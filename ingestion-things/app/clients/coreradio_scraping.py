from bs4 import BeautifulSoup, NavigableString
import httpx
from typing import List, Dict, Optional
import re

class CoreRadioClient:
    def __init__(self):
        self.base_url = "https://coreradio.online"
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=30.0,
            follow_redirects=True
        )
    
    def get_new_releases(self) -> List[Dict]:
        """
        Scrape new releases from CoreRadio
        """
        releases = []
        url = self.base_url
        
        try:
            response = self.client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Debug: print what we found
            print(f"Response status: {response.status_code}")
            print(f"Content length: {len(response.text)}")
            
            # The site uses DataLife Engine (DLE)
            # Each news item is typically in a div with class 'base' or similar
            # Let's try multiple selectors
            
            # Try to find all divs that contain both an image and genre text
            candidates = []
            
            # Look for img tags with spotify or music-related images
            imgs = soup.find_all('img')
            print(f"Found {len(imgs)} images")
            
            for img in imgs:
                # Check if this image is followed by or contains genre info
                parent = img.find_parent()
                if not parent:
                    continue
                
                # Look for the text pattern "Genre:" nearby
                text_content = parent.get_text()
                if 'Genre:' in text_content and 'Country:' in text_content:
                    candidates.append(parent)
            
            print(f"Found {len(candidates)} candidate containers")
            
            # If that didn't work, try finding all elements containing "Genre:"
            if not candidates:
                # Find all text nodes containing Genre and get their parent containers
                for elem in soup.find_all(text=re.compile(r'Genre:')):
                    parent = elem.find_parent(['div', 'article', 'section'])
                    if parent and parent not in candidates:
                        candidates.append(parent)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_candidates = []
            for c in candidates:
                # Use the text content as a hash to deduplicate
                text = c.get_text(strip=True)
                if text and text not in seen:
                    seen.add(text)
                    unique_candidates.append(c)
            
            print(f"Processing {len(unique_candidates)} unique containers")
            
            for container in unique_candidates:
                release = self._parse_container(container)
                if release:
                    releases.append(release)
                    
        except Exception as e:
            print(f"Error scraping: {e}")
            import traceback
            traceback.print_exc()
        
        return releases
    
    def _parse_container(self, container) -> Optional[Dict]:
        """
        Extract data from a container element.
        The title is in the img alt attribute, e.g.:
          alt="Magnolia Park - Dangerous [single] (2026)"
        """
        try:
            # --- Title from img alt ---
            title = None
            band = None
            album = None
            cover_url = None
            post_url = None

            img = container.find('img')
            if img:
                alt = img.get('alt', '')
                if alt and (' - ' in alt or ' – ' in alt or ' — ' in alt):
                    title = alt
                    band, album = self._parse_title(alt)

                # Cover image: prefer non-placeholder src
                for i in container.find_all('img'):
                    src = i.get('data-src') or i.get('src') or ''
                    if src and 'no_image.jpg' not in src and 'templates/coredark' not in src:
                        cover_url = src
                        break

            if not band:
                return None

            # --- Post URL from anchor ---
            a = container.find('a', href=True)
            if a:
                post_url = a['href']

            # --- Metadata from text (Genre / Country / Quality) ---
            text_block = container.get_text(separator=' ', strip=True)

            genres = []
            genre_match = re.search(r'Genre:\s*(.+?)(?:Country:|Quality:|$)', text_block)
            if genre_match:
                genres = [g.strip() for g in re.split(r'[/,]', genre_match.group(1)) if g.strip()]

            country = None
            country_match = re.search(r'Country:\s*(.+?)(?:Quality:|$)', text_block)
            if country_match:
                country = country_match.group(1).strip()

            quality = None
            quality_match = re.search(r'Quality:\s*(.+?)$', text_block)
            if quality_match:
                quality = quality_match.group(1).strip()

            return {
                "band": band,
                "album": album,
                "genres": genres,
                "country": country,
                "quality": quality,
                "cover_url": cover_url,
                "post_url": post_url,
                "source": "coreradio",
                "raw_title": title
            }

        except Exception as e:
            print(f"Error parsing container: {e}")
            return None
    
    def _parse_title(self, title: str) -> tuple:
        """
        Parse "Band - Album" format
        """
        # Remove backslash escapes
        title = title.replace('\\', '')
        
        # Try different dash types
        for separator in [' - ', ' – ', ' — ']:
            if separator in title:
                parts = title.split(separator, 1)
                band = parts[0].strip()
                album = parts[1].strip()
                # Remove [single], (2025), etc. from album name for cleaner output
                album_clean = re.sub(r'\s*[\(\[][^)\]]+[\)\]]\s*$', '', album).strip()
                return band, album_clean
        
        return title.strip(), "Unknown"
    
    def search_band(self, band_name: str) -> List[Dict]:
        """
        Search for specific band on CoreRadio
        """
        url = f"{self.base_url}/index.php?do=search"
        
        try:
            response = self.client.post(
                url,
                data={
                    'do': 'search',
                    'subaction': 'search',
                    'story': band_name
                }
            )
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Use same parsing logic
            releases = []
            candidates = []
            
            for elem in soup.find_all(text=re.compile(r'Genre:')):
                parent = elem.find_parent(['div', 'article', 'section'])
                if parent and parent not in candidates:
                    candidates.append(parent)
            
            for container in candidates:
                release = self._parse_container(container)
                if release and band_name.lower() in release['band'].lower():
                    releases.append(release)
            
            return releases
            
        except Exception as e:
            print(f"Error searching: {e}")
            return []


if __name__ == "__main__":
    client = CoreRadioClient()
    releases = client.get_new_releases()
    
    print(f"\n{'='*60}")
    print(f"FOUND {len(releases)} RELEASES")
    print(f"{'='*60}\n")
    
    for i, release in enumerate(releases[:10], 1):  # Show first 10
        print(f"{i}. {release['band']} - {release['album']}")
        if release['genres']:
            print(f"   Genre: {', '.join(release['genres'])}")
        if release['country']:
            print(f"   Country: {release['country']}")
        if release['quality']:
            print(f"   Quality: {release['quality']}")
        if release['cover_url']:
            print(f"   Cover: {release['cover_url']}")
        print()