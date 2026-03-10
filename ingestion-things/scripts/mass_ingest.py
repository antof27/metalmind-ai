import os
import sys
import time
import json
from typing import Set, List

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.orchestrator import StorageOrchestrator
from app.core.collector import UnifiedCollector

# File paths for saving state
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
QUEUE_FILE = os.path.join(STATE_DIR, "ingest_queue.json")
PROCESSED_FILE = os.path.join(STATE_DIR, "processed_bands.json")
FAILED_FILE = os.path.join(STATE_DIR, "failed_bands.json")

# Constants
SLEEP_SECONDS = 6  # Be kind to MusicBrainz and Last.fm
MAX_QUEUE_SIZE = 5000  # Prevent the queue from growing infinitely

# Initial seed list of influential metal bands to kickstart the crawl
SEED_BANDS = [
    "Black Sabbath", "Judas Priest", "Iron Maiden", 
    "Metallica", "Slayer", "Megadeth", "Anthrax", 
    "Death", "Morbid Angel", "Cannibal Corpse", 
    "Opeth", "Meshuggah", "Gojira", "Mastodon", 
    "Emperor", "Darkthrone", "Mayhem", 
    "At the Gates", "In Flames", "Dark Tranquillity",
    "Sleep", "Electric Wizard", "Kyuss",
    "Nightwish", "Blind Guardian", "Helloween"
]


class MassIngester:
    def __init__(self):
        print("🚀 Initialising Mass Ingester...")
        os.makedirs(STATE_DIR, exist_ok=True)
        
        self.orchestrator = StorageOrchestrator()
        self.collector = UnifiedCollector()
        
        self.queue: List[str] = []
        self.processed: Set[str] = set()
        self.failed: Set[str] = set()
        
        self._load_state()

    def _load_state(self):
        """Load queue and processed lists from disk to resume where we left off."""
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, 'r') as f:
                self.processed = set(json.load(f))
                
        if os.path.exists(FAILED_FILE):
            with open(FAILED_FILE, 'r') as f:
                self.failed = set(json.load(f))

        if os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE, 'r') as f:
                self.queue = json.load(f)
        else:
            # If no queue exists, use the seed bands
            self.queue = SEED_BANDS.copy()
            
        # Clean the queue just in case
        self.queue = [b for b in self.queue if b not in self.processed and b not in self.failed]
        
        print(f"📥 Loaded state: {len(self.processed)} processed, {len(self.failed)} failed, {len(self.queue)} in queue.")

    def _save_state(self):
        """Save current progress to disk."""
        with open(PROCESSED_FILE, 'w') as f:
            json.dump(list(self.processed), f, indent=2)
            
        with open(FAILED_FILE, 'w') as f:
            json.dump(list(self.failed), f, indent=2)
            
        with open(QUEUE_FILE, 'w') as f:
            json.dump(self.queue, f, indent=2)

    def crawl(self):
        """Main loop: pop a band, ingest it, add similar bands, wait, repeat."""
        print(f"\n🕷️  Starting crawl loop. Press CTRL+C to stop.")
        print(f"⏱️  Sleeping {SLEEP_SECONDS} seconds between bands to prevent IP bans.\n")
        
        try:
            while self.queue:
                band_name = self.queue.pop(0)
                
                if band_name in self.processed or band_name in self.failed:
                    continue
                    
                print(f"[{len(self.queue)} left] ──► Processing: {band_name}")
                
                # Step 1: Collect Data
                try:
                    band_data = self.collector.collect(band_name)
                    
                    # Safety check: if MusicBrainz didn't find anything, skip
                    if not band_data.get("mbid") or not band_data.get("name"):
                        print(f"   ⚠️  Could not find valid data for '{band_name}'. Marking as failed.")
                        self.failed.add(band_name)
                        self._save_state()
                        time.sleep(2)
                        continue
                        
                    # Fix: Make sure we register the actual normalized name
                    actual_name = band_data["name"]
                    
                    # Step 2: Store in DBs
                    result = self.orchestrator.ingest_band_complete(band_data)
                    
                    if result["status"] == "success":
                        self.processed.add(band_name)
                        if actual_name != band_name:
                            self.processed.add(actual_name)
                            
                        # Step 3: Expand the queue
                        new_similar = 0
                        for sim_band in band_data.get("similar_artists", []):
                            if (sim_band not in self.processed and 
                                sim_band not in self.failed and 
                                sim_band not in self.queue and
                                len(self.queue) < MAX_QUEUE_SIZE):
                                self.queue.append(sim_band)
                                new_similar += 1
                                
                        print(f"   🌱 Added {new_similar} new similar bands to queue.")
                    else:
                        print(f"   ❌ Ingestion failed for {band_name}: {result.get('errors')}")
                        self.failed.add(band_name)
                        
                except Exception as e:
                    print(f"   💥 Severe error processing {band_name}: {e}")
                    self.failed.add(band_name)
                
                # Save progress after every band
                self._save_state()
                
                # RATE LIMITING: Sleep so APIs don't block us
                print(f"   💤 Sleeping {SLEEP_SECONDS}s...\n")
                time.sleep(SLEEP_SECONDS)
                
            print("\n🎉 Queue is empty! Crawl finished.")
            
        except KeyboardInterrupt:
            print("\n\n🛑 Crawl paused by user.")
            self._save_state()
            print("💾 State saved. Run this script again to resume where you left off.")
        finally:
            self.orchestrator.close()


if __name__ == "__main__":
    ingester = MassIngester()
    ingester.crawl()
