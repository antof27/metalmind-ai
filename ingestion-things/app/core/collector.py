"""
UnifiedCollector — gathers data from all API sources for one band
and merges them into a single band_data dict that DocumentBuilder
and the StorageOrchestrator understand.

Data flow:
    MusicBrainz ──► official metadata (mbid, releases, lineup)
    Last.fm     ──► bio, listener stats, similar artists
    Reddit      ──► community posts and mentions
                         │
                         ▼
                 merged band_data dict
                         │
                         ▼
              DocumentBuilder  →  Chroma + Neo4j
"""

import os
import sys
import time
from typing import Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.clients.musicbrainz import MusicBrainzClient
from app.clients.lastfm import LastFMClient
from app.clients.reddit import RedditClient
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

        print("✅ UnifiedCollector ready")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def collect(self, band_name: str) -> Dict:
        """
        Collect and merge all data for a band.

        Returns a band_data dict with keys:
            name, mbid, genres, country, formed_year, disbanded_year,
            biography, albums, lineup, similar_artists,
            reddit_posts, reddit_mentions, popularity_score
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

        # 4 — Compute a simple popularity score
        band_data["popularity_score"] = self._compute_popularity(band_data)

        print(f"   ✅ Collected: {band_data['name']} | "
              f"{len(band_data.get('albums', []))} albums | "
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
            "lineup": [],
            "similar_artists": [],
            "reddit_posts": [],
            "reddit_mentions": 0,
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

            # Releases (albums)
            releases = self.musicbrainz.get_releases(mbid, release_type="album", limit=25)
            band_data["albums"] = [
                {
                    "title": r.get("title"),
                    "year": int(r.get("date", "0")[:4]) if r.get("date") else None,
                    "type": "album",
                    "mbid": r.get("id"),
                }
                for r in releases
            ]

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
                  f"| {len(band_data['albums'])} releases")

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
