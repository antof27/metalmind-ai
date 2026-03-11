"""
GeniusClient — fetches song lyrics via the Genius API.
Uses the `lyricsgenius` library.

Setup:
    pip install lyricsgenius
    Add to .env:  GENIUS_ACCESS_TOKEN=your_token_here
"""

import os
import re
import time
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())


class GeniusClient:
    """
    Thin wrapper around lyricsgenius for fetching lyrics.
    Handles missing tokens gracefully (returns None / empty lists).
    """

    #: Maximum chars to store per lyric snippet (keeps Chroma docs focused)
    MAX_LYRICS_CHARS = 3600

    def __init__(self):
        self.token = os.getenv("GENIUS_ACCESS_TOKEN")
        self._genius = None

        if not self.token:
            raise ValueError(
                "GENIUS_ACCESS_TOKEN not set. "
                "Get a free token at https://genius.com/api-clients and add it to .env"
            )

        try:
            import lyricsgenius
            self._genius = lyricsgenius.Genius(
                self.token,
                skip_non_songs=True,
                excluded_terms=["(Remix)", "(Live)", "(Acoustic)", "(Demo)"],
                remove_section_headers=True,
                verbose=False,
                timeout=10,
            )
            print("✅ Genius client initialized")
        except ImportError:
            raise ImportError("lyricsgenius not installed. Run: pip install lyricsgenius")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get_artist_top_songs(
        self, artist_name: str, limit: int = 1000
    ) -> List[Dict]:
        """
        Fetch top songs with lyrics for an artist.

        Returns a list of dicts:
            {title, lyrics, lyrics_snippet, url}
        """
        if not self._genius:
            return []

        try:
            # lyricsgenius searches and fetches lyrics in one call
            artist = self._genius.search_artist(
                artist_name,
                max_songs=limit,
                sort="popularity",
                get_full_info=False,
            )
            if not artist or not artist.songs:
                return []

            songs = []
            for song in artist.songs:
                lyrics = self._clean_lyrics(song.lyrics or "")
                if not lyrics:
                    continue
                songs.append({
                    "title": song.title,
                    "lyrics": lyrics,
                    "lyrics_snippet": lyrics[: self.MAX_LYRICS_CHARS],
                    "url": song.url,
                })
            return songs

        except Exception as e:
            print(f"   ⚠️  Genius error for '{artist_name}': {e}")
            return []

    def get_song_lyrics(self, artist_name: str, song_title: str) -> Optional[str]:
        """
        Fetch lyrics for a specific song.
        Returns cleaned lyric text or None if not found.
        """
        if not self._genius:
            return None
        try:
            song = self._genius.search_song(song_title, artist_name)
            if not song:
                return None
            return self._clean_lyrics(song.lyrics or "")[: self.MAX_LYRICS_CHARS]
        except Exception as e:
            print(f"   ⚠️  Genius error for '{song_title}': {e}")
            return None

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _clean_lyrics(self, raw: str) -> str:
        """
        Strip Genius boilerplate:
        - "X Contributors" header line
        - [Verse], [Chorus], [Bridge] section tags
        - Trailing "Embed" / URL lines
        """
        # Remove "N Contributors\nTitle Lyrics" header lines
        raw = re.sub(r"^\d+ Contributors.*?\n", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"^.*?Lyrics\n", "", raw, flags=re.IGNORECASE)
        # Remove section headers like [Verse 1], [Pre-Chorus]
        raw = re.sub(r"\[.*?\]", "", raw)
        # Remove trailing "Embed" line
        raw = re.sub(r"\d*Embed$", "", raw.strip(), flags=re.IGNORECASE)
        # Collapse multiple blank lines
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


# Smoke test
if __name__ == "__main__":
    client = GeniusClient()
    songs = client.get_artist_top_songs("Black Sabbath", limit=3)
    for s in songs:
        print(f"\n🎵 {s['title']}")
        print(s["lyrics_snippet"][:300])
