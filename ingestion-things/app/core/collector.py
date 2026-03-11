"""
UnifiedCollector — gathers data from all API sources for one band
and merges them into a single band_data dict that DocumentBuilder
and the StorageOrchestrator understand.
"""

import os
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.clients.musicbrainz import MusicBrainzClient
from app.clients.lastfm import LastFMClient
from app.clients.reddit import RedditClient
from app.clients.acousticbrainz import TrackEnricher
from dotenv import load_dotenv

load_dotenv()


class UnifiedCollector:
    """
    Orchestrates data collection from multiple APIs for a single band.
    Call collect(band_name) to get a merged band_data dict.
    """

    def __init__(self):
        print("🔌 Initialising UnifiedCollector...")
        self.musicbrainz = MusicBrainzClient(
            user_agent="MetalMind/0.1.0 (antosw2000@gmail.com)"
        )
        try:
            self.lastfm = LastFMClient()
        except ValueError as e:
            print(f"   ⚠️  Last.fm unavailable: {e}")
            self.lastfm = None

        try:
            self.reddit = RedditClient()
        except Exception as e:
            print(f"   ⚠️  Reddit unavailable: {e}")
            self.reddit = None

        # Genius — requires GENIUS_ACCESS_TOKEN in .env
        try:
            from app.clients.genius import GeniusClient
            self.genius = GeniusClient()
        except (ValueError, ImportError) as e:
            print(f"   ⚠️  Genius unavailable: {e}")
            self.genius = None

        # AcousticBrainz — no key needed, always initialised
        self.track_enricher = TrackEnricher(cache_dir="scripts/ab_cache")

        print("✅ UnifiedCollector ready")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def collect(self, band_name: str) -> Dict:
        """
        Collect and merge all data for a band.

        Returns a band_data dict with keys:
            name, mbid, genres, country, formed_year, disbanded_year,
            biography, releases, albums, eps, singles, lineup,
            similar_artists, reddit_posts, reddit_mentions,
            top_tracks, popularity_score
        """
        print(f"\n🔍 Collecting data for: {band_name}")

        # 1 — MusicBrainz (primary source of truth)
        band_data = self._collect_musicbrainz(band_name)

        # 2 — Last.fm (bio enrichment, stats, similar artists)
        if self.lastfm:
            band_data = self._enrich_lastfm(band_data)

        # 3 — Reddit (community sentiment)
        if self.reddit:
            band_data = self._enrich_reddit(band_data)

        # 4 — Last.fm album wiki descriptions (free, no extra key)
        if self.lastfm:
            band_data = self._enrich_album_descriptions(band_data)

        # 5 — Genius (lyrics for top tracks)
        if self.genius:
            band_data = self._enrich_genius(band_data)

        # 6 — AcousticBrainz (audio features per track, no key needed)
        band_data = self._enrich_acousticbrainz(band_data)

        # 7 — Compute a simple popularity score
        band_data["popularity_score"] = self._compute_popularity(band_data)

        print(f"   ✅ Collected: {band_data['name']} | "
              f"{len(band_data.get('albums', []))} albums | "
              f"{len(band_data.get('top_tracks', []))} enriched tracks | "
              f"{len(band_data.get('reddit_posts', []))} reddit posts")

        return band_data

    # =========================================================================
    # STEP 1 — MUSICBRAINZ
    # =========================================================================

    def _collect_musicbrainz(self, band_name: str) -> Dict:
        """Build base band_data from MusicBrainz."""
        band_data: Dict = {
            "name": band_name,
            "mbid": None,
            "genres": [],
            "country": None,
            "formed_year": None,
            "disbanded_year": None,
            "biography": "",
            "albums": [],
            "eps": [],
            "singles": [],
            "lineup": [],
            "similar_artists": [],
            "reddit_posts": [],
            "reddit_mentions": 0,
            "top_tracks": [],      # populated by Genius / AcousticBrainz
        }

        try:
            # Search for the artist
            results = self.musicbrainz.search_artist(band_name, limit=5)
            if not results:
                print(f"   ⚠️  MusicBrainz: no results for '{band_name}'")
                return band_data

            # Pick the best match by name similarity
            artist = self._best_match(results, band_name)
            mbid = artist.get("id")
            band_data["mbid"] = mbid

            # Fetch full artist details
            details = self.musicbrainz.get_artist(mbid)
            band_data["name"] = details.get("name", band_name)
            band_data["country"] = details.get("country")

            # Life span
            lifespan = details.get("life-span", {})
            begin = lifespan.get("begin", "")
            end = lifespan.get("end", "")
            if begin:
                band_data["formed_year"] = int(begin[:4]) if len(begin) >= 4 else None
            if end:
                band_data["disbanded_year"] = int(end[:4]) if len(end) >= 4 else None

            # Tags → genres
            tags = details.get("tags", [])
            band_data["genres"] = [
                t["name"] for t in sorted(tags, key=lambda x: x.get("count", 0), reverse=True)
                if t.get("count", 0) > 0
            ][:5]

            # Releases (Albums, EPs, Singles, etc)
            releases = self.musicbrainz.get_releases(mbid)
            
            # Identify the proper type of each release
            exclude_words = ["best of", "collection", "soundtrack", "interview", "compilation", "greatest hits", "essential", "anthology", "demo", "broadcast"]
            
            processed_releases = []
            for r in releases:
                title = r.get("title", "")
                primary = r.get("primary-type", "Unknown")
                secondary = r.get("secondary-types", [])
                
                # Determine explicit type
                if "Compilation" in secondary or any(w in title.lower() for w in exclude_words):
                    rel_type = "Compilation"
                elif "Live" in secondary or "live" in title.lower():
                    rel_type = "Live"
                else:
                    rel_type = primary  # "Album", "EP", "Single", etc.
                
                # Safer date parsing
                release_date = r.get("first-release-date", "") or r.get("date", "")
                year = None
                if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
                    year = int(release_date[:4])
                
                processed_releases.append({
                    "title": title,
                    "year": year,
                    "type": rel_type,
                    "mbid": r.get("id"),
                }
            )

            band_data["releases"] = processed_releases
            band_data["albums"] = [r for r in processed_releases if r["type"] == "Album"]
            band_data["eps"] = [r for r in processed_releases if r["type"] == "EP"]
            band_data["singles"] = [r for r in processed_releases if r["type"] == "Single"]

            # Artist relationships → band members
            for rel in details.get("relations", []):
                if rel.get("type") == "member of band" and rel.get("direction") == "backward":
                    artist_rel = rel.get("artist", {})
                    attrs = rel.get("attributes", [])
                    band_data["lineup"].append({
                        "name": artist_rel.get("name"),
                        "role": ", ".join(attrs) if attrs else "member",
                        "join_year": int(rel.get("begin", "0")[:4]) if rel.get("begin") else None,
                        "leave_year": int(rel.get("end", "0")[:4]) if rel.get("end") else None,
                    })


            print(f"   ✅ MusicBrainz: {band_data['name']} ({band_data['country']}) "
                f"| {len(band_data['albums'])} albums "
                f"| {len(band_data['eps'])} EPs "
                f"| {len(band_data['singles'])} singles "
                f"| {len(band_data.get('releases', []))} total releases")
        except Exception as e:
            print(f"   ❌ MusicBrainz error: {e}")

        return band_data
    # =========================================================================
    # STEP 2 — LAST.FM
    # =========================================================================

    def _enrich_lastfm(self, band_data: Dict) -> Dict:
        """Enrich band_data with Last.fm bio, stats, and similar artists."""
        try:
            info = self.lastfm.get_artist_info(
                band_data["name"],
                mbid=band_data.get("mbid")
            )

            # Bio
            bio = info.get("bio", {}).get("summary", "")
            if bio and not band_data.get("biography"):
                # Strip Last.fm boilerplate link at the end
                bio = bio.split("<a href")[0].strip()
                band_data["biography"] = bio

            # Listener stats → used for popularity
            stats = info.get("stats", {})
            band_data["listeners"] = int(stats.get("listeners", 0))
            band_data["playcount"] = int(stats.get("playcount", 0))

            # Tags (may add genres not in MusicBrainz)
            tags = [t["name"] for t in info.get("tags", {}).get("tag", [])]
            existing = set(g.lower() for g in band_data["genres"])
            for tag in tags:
                if tag.lower() not in existing and len(band_data["genres"]) < 8:
                    band_data["genres"].append(tag)
                    existing.add(tag.lower())

            # Similar artists
            similar = self.lastfm.get_similar_artists(band_data["name"], limit=10)
            band_data["similar_artists"] = [s.get("name") for s in similar]

            print(f"   ✅ Last.fm: {band_data['listeners']:,} listeners | "
                  f"{len(band_data['similar_artists'])} similar artists")

        except Exception as e:
            print(f"   ⚠️  Last.fm error: {e}")

        return band_data

    # =========================================================================
    # STEP 3 — REDDIT
    # =========================================================================

    def _enrich_reddit(self, band_data: Dict) -> Dict:
        """Add Reddit posts and mention count."""
        try:
            posts = self.reddit.search_band_mentions(band_data["name"], limit=20)
            band_data["reddit_posts"] = posts
            band_data["reddit_mentions"] = len(posts)
            print(f"   ✅ Reddit: {len(posts)} posts mentioning {band_data['name']}")
        except Exception as e:
            print(f"   ⚠️  Reddit error: {e}")

        return band_data

    # =========================================================================
    # STEP 4 — LAST.FM ALBUM DESCRIPTIONS
    # =========================================================================

    def _enrich_album_descriptions(self, band_data: Dict) -> Dict:
        """
        Fetch per-album wiki descriptions from Last.fm and attach them
        to the corresponding release in band_data['releases'].
        Only fetches for the top 4 albums (rate-limit friendly).
        """
        try:
            albums = [r for r in band_data.get("releases", []) if r.get("type") == "Album"]
            for album in albums[:4]:
                title = album.get("title", "")
                try:
                    info = self.lastfm.get_album_info(band_data["name"], title)
                    wiki = info.get("wiki", {}).get("summary", "")
                    if wiki:
                        # Strip Last.fm boilerplate link
                        wiki = wiki.split("<a href")[0].strip()
                        album["description"] = wiki[:600]
                    tracks = info.get("tracks", {}).get("track", [])
                    if isinstance(tracks, list):
                        album["track_list"] = [t.get("name") for t in tracks]
                    elif isinstance(tracks, dict):
                        album["track_list"] = [tracks.get("name")]
                except Exception:
                    pass  # some albums won't be found — skip silently
                time.sleep(1)  # respect Last.fm rate limit

            print(f"   ✅ Last.fm album descriptions: enriched {min(len(albums), 4)} albums")
        except Exception as e:
            print(f"   ⚠️  Last.fm album description error: {e}")
        return band_data

    # =========================================================================
    # STEP 5 — GENIUS LYRICS
    # =========================================================================

    def _enrich_genius(self, band_data: Dict) -> Dict:
        """
        Fetch lyrics for the top 5 popular songs and attach them
        to band_data['top_tracks'].
        """
        try:
            songs = self.genius.get_artist_top_songs(band_data["name"], limit=1000)
            for song in songs:
                band_data["top_tracks"].append({
                    "title": song["title"],
                    "mbid": None,          # may be filled by AcousticBrainz step
                    "lyrics_snippet": song["lyrics_snippet"],
                    "url": song.get("url"),
                    "sound_description": "",  # filled by AcousticBrainz step
                })
            print(f"   ✅ Genius: {len(songs)} songs with lyrics")
        except Exception as e:
            print(f"   ⚠️  Genius error: {e}")
        return band_data

    # =========================================================================
    # STEP 6 — ACOUSTICBRAINZ AUDIO FEATURES
    # =========================================================================

    def _enrich_acousticbrainz(self, band_data: Dict) -> Dict:
        """
        Produce dense audio features from AcousticBrainz via TrackEnricher
        for each track in band_data['top_tracks'] that has an MBID.
        """
        try:
            tracks = band_data.get("top_tracks", [])
            for track in tracks:
                if not track.get("mbid") and track.get("title"):
                    mbid = self.musicbrainz.search_recording(track["title"], band_data.get("name"))
                    if mbid:
                        track["mbid"] = mbid

            enriched = self.track_enricher.enrich(tracks)
            band_data["top_tracks"] = enriched
            found = sum(1 for t in enriched if t.get("embedding"))
            print(f"   ✅ AcousticBrainz: {found}/{len(enriched)} tracks with audio embeddings")

        except Exception as e:
            print(f"   ⚠️  AcousticBrainz error: {e}")
        return band_data

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _best_match(self, results: List[Dict], name: str) -> Dict:
        """Return the result whose name most closely matches the query."""
        name_lower = name.lower()
        for r in results:
            if r.get("name", "").lower() == name_lower:
                return r
        return results[0]

    def _compute_popularity(self, band_data: Dict) -> float:
        """
        Simple 0-100 popularity score combining listeners + reddit activity.
        Caps at 100.
        """
        listeners = band_data.get("listeners", 0)
        reddit = band_data.get("reddit_mentions", 0)
        score = min(listeners / 100_000, 80) + min(reddit * 2, 20)
        return round(score, 2)


# Smoke test
if __name__ == "__main__":
    collector = UnifiedCollector()
    band_data = collector.collect("Opeth")

    print(f"\n{'='*60}")
    print(f"Band:    {band_data['name']}")
    print(f"MBID:    {band_data['mbid']}")
    print(f"Country: {band_data['country']}")
    print(f"Formed:  {band_data['formed_year']}")
    print(f"Genres:  {band_data['genres']}")
    print(f"Albums:  {len(band_data['albums'])}")
    print(f"Members: {len(band_data['lineup'])}")
    print(f"Reddit:  {band_data['reddit_mentions']} posts")
    print(f"Score:   {band_data['popularity_score']}")
    print(f"Bio:     {band_data['biography'][:200]}...")
