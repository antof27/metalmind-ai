import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings


class ChromaClientLocal:
    """
    Thin wrapper around ChromaDB.
    Defines the 5 canonical collections used by the orchestrator:
        bands, albums, members, reddit, genres
    The orchestrator writes embeddings directly into these collections.
    """

    COLLECTIONS = ["bands", "releases", "members", "reddit", "genres"]

    def __init__(self, persist_dir: str = None):
        self.persist_dir = persist_dir or os.getenv("CHROMA_PATH", "./chroma_data")
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Create / open all collections at startup
        self.collections = {
            name: self._get_or_create(name)
            for name in self.COLLECTIONS
        }

        for name, coll in self.collections.items():
            print(f"   📚 {name}: {coll.count()} documents")

    def _get_or_create(self, name: str):
        try:
            return self.client.get_collection(name)
        except Exception:
            return self.client.create_collection(
                name=name,
                metadata={"description": f"metalmind {name}"}
            )

    def get_stats(self) -> Dict:
        """Return document counts per collection."""
        return {name: coll.count() for name, coll in self.collections.items()}

    def reset(self):
        """Wipe all collections (useful for testing)."""
        self.client.reset()
        self.collections = {
            name: self._get_or_create(name)
            for name in self.COLLECTIONS
        }


# Smoke test
if __name__ == "__main__":
    client = ChromaClientLocal()
    print(f"\nStats: {client.get_stats()}")
