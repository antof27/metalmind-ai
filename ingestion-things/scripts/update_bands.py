import os
import sys
import time
import json
from typing import Set, List

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.orchestrator import StorageOrchestrator
from app.core.collector import UnifiedCollector

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
PROCESSED_FILE = os.path.join(STATE_DIR, "processed_bands.json")
SLEEP_SECONDS = 6

class BandUpdater:
    def __init__(self):
        print("🔄 Initialising Band Updater...")
        self.orchestrator = StorageOrchestrator()
        self.collector = UnifiedCollector()
        self.bands_to_update: List[str] = []
        self._load_state()

    def _load_state(self):
        """Load processed bands to update them."""
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, 'r') as f:
                self.bands_to_update = json.load(f)
        else:
            print("⚠️ No processed_bands.json found. Run mass_ingest.py first!")

        print(f"📥 Loaded {len(self.bands_to_update)} bands to update.")

    def run_update(self):
        """Update loop: re-ingest each band to upsert latest releases and Reddit posts."""
        if not self.bands_to_update:
            return

        print(f"\\n🚀 Starting update loop. Press CTRL+C to stop.")
        print(f"⏱️ Sleeping {SLEEP_SECONDS} seconds between bands.\\n")

        try:
            for index, band_name in enumerate(self.bands_to_update):
                print(f"[{index + 1}/{len(self.bands_to_update)}] ──► Updating: {band_name}")

                try:
                    band_data = self.collector.collect(band_name)

                    if not band_data.get("mbid") or not band_data.get("name"):
                        print(f"   ⚠️ Could not find valid data for '{band_name}'. Skipping.")
                        continue

                    # The orchestrator's upsert to Chroma and Neo4j's MERGE naturally handle updates
                    result = self.orchestrator.ingest_band_complete(band_data)

                    if result["status"] == "success":
                        print(f"   ✅ Successfully updated {band_name}!")
                    else:
                        print(f"   ❌ Update failed for {band_name}: {result.get('errors')}")

                except Exception as e:
                    print(f"   💥 Error updating {band_name}: {e}")

                print(f"   💤 Sleeping {SLEEP_SECONDS}s...\\n")
                time.sleep(SLEEP_SECONDS)

            print("\\n🎉 Update loop finished.")

        except KeyboardInterrupt:
            print("\\n\\n🛑 Update paused by user.")
        finally:
            self.orchestrator.close()

if __name__ == "__main__":
    updater = BandUpdater()
    updater.run_update()
