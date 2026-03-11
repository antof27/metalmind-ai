import time
import httpx
from typing import List, Dict, Optional
from httpx import ConnectError, HTTPStatusError


class MusicBrainzClient:
    def __init__(self, user_agent: str = None):
        self.base_url = "https://musicbrainz.org/ws/2"
        self.user_agent = user_agent or "MetalMind/0.1.0 (change@this.email)"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json"
        }
        # http2=False prevents [SSL: UNEXPECTED_EOF_WHILE_READING] errors
        # caused by httpx attempting ALPN/HTTP2 negotiation with servers that don't support it
        self.client = httpx.Client(headers=self.headers, timeout=30.0, http2=False)
        self.last_request_time = 0
        self.min_delay = 1.0

    def _rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self.last_request_time = time.time()

    def _get(self, url: str, params: dict, retries: int = 3) -> dict:
        """GET with retry logic for transient SSL/connection errors."""
        for attempt in range(retries):
            try:
                self._rate_limit()
                response = self.client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except ConnectError as e:
                if attempt < retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    print(f"Connection error (attempt {attempt + 1}/{retries}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
            except HTTPStatusError as e:
                if e.response.status_code == 503 and attempt < retries - 1:
                    wait = 2 ** attempt
                    print(f"Rate limited (503), retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

    def search_artist(self, name: str, limit: int = 5) -> List[Dict]:
        url = f"{self.base_url}/artist"
        params = {"query": name, "limit": limit, "fmt": "json"}
        return self._get(url, params).get("artists", [])
        
    def search_recording(self, track_title: str, artist_name: str, limit: int = 1) -> Optional[str]:
        """Search for a recording MBID by track title and artist name."""
        url = f"{self.base_url}/recording"
        query = f'recording:"{track_title}" AND artist:"{artist_name}"'
        params = {"query": query, "limit": limit, "fmt": "json"}
        recordings = self._get(url, params).get("recordings", [])
        if recordings:
            return recordings[0].get("id")
        return None

    def get_artist(self, mbid: str) -> Dict:
        """Get full artist details by MusicBrainz ID"""
        url = f"{self.base_url}/artist/{mbid}"
        params = {
            "inc": "tags+aliases+artist-rels+url-rels+release-groups",
            "fmt": "json"
        }
        return self._get(url, params)
    
    def get_releases(self, mbid: str, types: List[str] = None) -> List[Dict]:
        url = f"{self.base_url}/release-group"
        all_releases = []
        offset = 0
        
        # Default: only fetch Albums and EPs, ignore singles/promos/etc
        type_filter = "|".join(types or ["album", "ep", "single"])

        while True:
            params = {
                "artist": mbid,
                "type": type_filter,   # ← filter at API level
                "limit": 100,
                "offset": offset,
                "fmt": "json"
            }
            data = self._get(url, params)
            page = data.get("release-groups", [])
            all_releases.extend(page)

            total = int(data.get("release-group-count", 0))
            offset += len(page)

            if offset >= total or not page:
                break

        return all_releases
        
    def browse_by_tag(self, tag: str, entity_type: str = "artist", limit: int = 25) -> List[Dict]:
        """Browse artists or releases by genre tag"""
        url = f"{self.base_url}/{entity_type}"
        params = {"tag": tag, "limit": limit, "fmt": "json"}
        return self._get(url, params).get(f"{entity_type}s", [])
    
    
# Example usage
if __name__ == "__main__":
    
    client = MusicBrainzClient(
        user_agent="MetalMind/0.1.0 (antosw2000@gmail.com)"
    )
    
    # Search for band
    results = client.search_artist("karmanjakah", limit=3)
    print(f"Found {len(results)} artists")
    
    for artist in results:
        print(f"- {artist['name']} ({artist.get('country', 'Unknown')})")