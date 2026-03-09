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
        Extract data from a container element
        """
        try:
            text = container.get_text(separator='\n', strip=True)
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            if not lines:
                return None
            
            # Debug
            # print(f"Parsing container with {len(lines)} lines")
            
            # Find the title line (usually contains " - " and doesn't start with Genre/Country/Quality)
            title = None
            band = None
            album = None
            
            for line in lines:
                # Skip metadata lines
                if any(line.startswith(x) for x in ['Genre:', 'Country:', 'Quality:', 'Load more', '«', '»']):
                    continue
                
                # Look for "Band - Album" pattern
                if ' - ' in line or ' – ' in line:
                    title = line
                    band, album = self._parse_title(line)
                    break
            
            if not band:
                return None
            
            # Extract metadata
            genres = []
            country = None
            quality = None
            
            full_text = ' '.join(lines)
            
            # Extract Genre
            genre_match = re.search(r'Genre:\s*([^\n]+?)(?:\s*Country:|$)', full_text)
            if genre_match:
                genre_text = genre_match.group(1).strip()
                genres = [g.strip() for g in re.split(r'[/,]', genre_text) if g.strip()]
            
            # Extract Country
            country_match = re.search(r'Country:\s*([^\n]+?)(?:\s*Quality:|$)', full_text)
            if country_match:
                country = country_match.group(1).strip()
            
            # Extract Quality
            quality_match = re.search(r'Quality:\s*([^\n]+?)(?:\n|$)', full_text)
            if quality_match:
                quality = quality_match.group(1).strip()
            
            # Get cover image - look for img tags in this container
            cover_url = None
            img = container.find('img')
            if img:
                # Prefer data-src (lazy loading) over src
                cover_url = img.get('data-src') or img.get('src')
                # Skip placeholder images
                if cover_url and ('no_image.jpg' in cover_url or 'templates/coredark' in cover_url):
                    # Try to find a better image - look for spotify or other CDNs
                    all_imgs = container.find_all('img')
                    for i in all_imgs:
                        src = i.get('data-src') or i.get('src')
                        if src and 'no_image.jpg' not in src and 'templates/coredark' not in src:
                            cover_url = src
                            break
            
            return {
                "band": band,
                "album": album,
                "genres": genres,
                "country": country,
                "quality": quality,
                "cover_url": cover_url,
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
            print(f"   Cover: {release['cover_url'][:80]}...")
        print()