
import os
import time
import httpx
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()  # Loads .env from the project root


class LastFMClient:
    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize Last.fm client
        
        Args:
            api_key: Your API key from https://www.last.fm/api/account
            api_secret: Shared secret (only needed for write operations/auth)
        """
        self.api_key = api_key or os.getenv("LASTFM_API_KEY")
        self.base_url = "https://ws.audioscrobbler.com/2.0/"
        self.client = httpx.Client(timeout=30.0)
        
        if not self.api_key:
            raise ValueError("Last.fm API key required. Get one at https://www.last.fm/api/account/create")
        
        print(f"✅ Last.fm client initialized")
    
    def _rate_limit(self):
        """Last.fm suggests 1 request per second for free tier"""
        time.sleep(2)
    
    def _make_request(self, method: str, **params) -> Dict:
        """Make authenticated request to Last.fm API"""
        self._rate_limit()
        
        # Add API key and format to all requests
        request_params = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **params
        }
        
        response = self.client.get(self.base_url, params=request_params)
        response.raise_for_status()
        
        data = response.json()
        
        # Check for API errors
        if "error" in data:
            raise Exception(f"Last.fm API error {data['error']}: {data.get('message', 'Unknown error')}")
        
        return data
    
    def search_artist(self, artist: str, limit: int = 10) -> List[Dict]:
        """Search for artists"""
        data = self._make_request("artist.search", artist=artist, limit=limit)
        results = data.get("results", {}).get("artistmatches", {}).get("artist", [])
        return results if isinstance(results, list) else [results]
    
    def get_artist_info(self, artist: str, mbid: str = None) -> Dict:
        """
        Get detailed artist info including:
        - Bio/summary
        - Tags (genres)
        - Similar artists
        - Stats (listeners, playcount)
        """
        params = {"artist": artist}
        if mbid:
            params["mbid"] = mbid  # MusicBrainz ID for precision
        
        data = self._make_request("artist.getInfo", **params)
        return data.get("artist", {})
    
    def get_artist_top_tags(self, artist: str) -> List[Dict]:
        """Get user-generated genre tags for an artist"""
        data = self._make_request("artist.getTopTags", artist=artist)
        tags = data.get("toptags", {}).get("tag", [])
        return tags if isinstance(tags, list) else [tags]
    
    def get_similar_artists(self, artist: str, limit: int = 20) -> List[Dict]:
        """Get similar artists based on Last.fm's algorithm"""
        data = self._make_request("artist.getSimilar", artist=artist, limit=limit)
        similar = data.get("similarartists", {}).get("artist", [])
        return similar if isinstance(similar, list) else [similar]
    
    def get_artist_top_albums(self, artist: str, limit: int = 20) -> List[Dict]:
        """Get top albums by an artist"""
        data = self._make_request("artist.getTopAlbums", artist=artist, limit=limit)
        albums = data.get("topalbums", {}).get("album", [])
        return albums if isinstance(albums, list) else [albums]
    
    def get_artist_top_tracks(self, artist: str, limit: int = 20) -> List[Dict]:
        """Get top tracks by an artist"""
        data = self._make_request("artist.getTopTracks", artist=artist, limit=limit)
        tracks = data.get("toptracks", {}).get("track", [])
        return tracks if isinstance(tracks, list) else [tracks]
    
    def get_tag_info(self, tag: str) -> Dict:
        """Get info about a genre/tag (e.g., "death metal")"""
        data = self._make_request("tag.getInfo", tag=tag)
        return data.get("tag", {})
    
    def get_top_artists_by_tag(self, tag: str, limit: int = 50) -> List[Dict]:
        """Get top artists for a genre (e.g., "progressive metal")"""
        data = self._make_request("tag.getTopArtists", tag=tag, limit=limit)
        artists = data.get("topartists", {}).get("artist", [])
        return artists if isinstance(artists, list) else [artists]
    
    def get_album_info(self, artist: str, album: str) -> Dict:
        """Get detailed album info including tracks"""
        data = self._make_request("album.getInfo", artist=artist, album=album)
        return data.get("album", {})


# Example usage
if __name__ == "__main__":
    # API key is loaded from .env automatically via load_dotenv() above
    client = LastFMClient()
    
    # Search for artist
    results = client.search_artist("karmanjakah")
    print(f"Found {len(results)} artists")
    
    # Get detailed info
    if results:
        info = client.get_artist_info(results[0]["name"])
        print(f"\nName: {info.get('name')}")
        print(f"Listeners: {info.get('stats', {}).get('listeners')}")
        print(f"Playcount: {info.get('stats', {}).get('playcount')}")
        
        tags = [t["name"] for t in info.get("tags", {}).get("tag", [])]
        print(f"Tags: {', '.join(tags)}")
        
        # Get similar artists
        similar = client.get_similar_artists(info["name"], limit=5)
        print(f"\nSimilar artists: {', '.join([a['name'] for a in similar])}")