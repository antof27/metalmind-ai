#!/usr/bin/env python3
"""
Local Integration Test — tests all components without Docker.
Run from the project root: python3 version/test_local.py
"""
import os
import sys
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "ingestion-things"))
sys.path.insert(0, os.path.join(ROOT, "ingestion-things", "app", "clients"))

load_dotenv(os.path.join(ROOT, ".env"))

print("=" * 60)
print("METALMIND LOCAL TEST")
print("=" * 60)

# ── Test 1: ChromaDB ──────────────────────────────────────────────────────────
print("\n1. Testing Local ChromaDB...")
try:
    from app.clients.chroma import ChromaClientLocal
    chroma = ChromaClientLocal()

    # Write directly into a collection (store_band was removed; orchestrator handles writes)
    coll = chroma.collections["bands"]
    coll.upsert(
        ids=["test-band-local"],
        embeddings=[[0.1] * 384],
        documents=["Test Band is a death metal band from US."],
        metadatas=[{"name": "Test Band", "mbid": "test-456", "country": "US"}],
    )
    print("   ✅ ChromaDB upsert: OK")
    print(f"   ✅ Stats: {chroma.get_stats()}")

except Exception as e:
    print(f"   ❌ ChromaDB Error: {e}")

# ── Test 2: Neo4j ─────────────────────────────────────────────────────────────
print("\n2. Testing Local Neo4j...")
try:
    from app.clients.neo4j_client import Neo4jClient
    neo4j = Neo4jClient()

    band_id = neo4j.create_band({
        "mbid": "test-neo-789",
        "name": "Test Band Neo",
        "formed_year": 1985,
        "country": "UK",
        "genres": ["thrash metal"],
    })
    print(f"   ✅ Create band: OK (id={band_id})")

    neo4j.create_album("test-neo-789", {"title": "Test Album", "year": 1990})
    print("   ✅ Create album: OK")

    neo4j.connect_genre("test-neo-789", "thrash metal")
    print("   ✅ Connect genre: OK")

    neo4j.create_member("test-neo-789", {"name": "Test Musician", "role": "guitar"})
    members = neo4j.get_band_members("test-neo-789")
    print(f"   ✅ Members: {members}")

    bands = neo4j.get_all_bands()
    print(f"   ✅ All bands: {len(bands)} found")

    neo4j.close()

except Exception as e:
    print(f"   ❌ Neo4j Error: {e}")

# ── Test 3: MusicBrainz API ───────────────────────────────────────────────────
print("\n3. Testing MusicBrainz API...")
try:
    from app.clients.musicbrainz import MusicBrainzClient
    mb = MusicBrainzClient(user_agent="MetalMind/0.1.0 (antosw2000@gmail.com)")
    results = mb.search_artist("Metallica", limit=1)
    print(f"   ✅ MusicBrainz: Found {len(results)} results for 'Metallica'")
except Exception as e:
    print(f"   ❌ MusicBrainz Error: {e}")

# ── Test 4: Last.fm API ────────────────────────────────────────────────────────
print("\n4. Testing Last.fm API...")
try:
    from app.clients.lastfm import LastFMClient
    lastfm = LastFMClient()
    info = lastfm.get_artist_info("Metallica")
    listeners = info.get("stats", {}).get("listeners", "?")
    print(f"   ✅ Last.fm: Metallica has {listeners} listeners")
except Exception as e:
    print(f"   ❌ Last.fm Error: {e}")

# ── Test 5: Full orchestrator ingestion ───────────────────────────────────────
print("\n5. Testing Orchestrator (ingestion + RAG)...")
try:
    from app.core.orchestrator import StorageOrchestrator
    orch = StorageOrchestrator()

    test_band = {
        "name": "Integration Test Band",
        "mbid": "inttest-001",
        "genres": ["death metal"],
        "country": "US",
        "formed_year": 1990,
        "biography": "A band created for integration testing purposes.",
        "albums": [{"title": "Test Album", "year": 2000}],
        "lineup": [{"name": "Test Musician", "role": "guitar"}],
        "reddit_mentions": 0,
    }

    result = orch.ingest_band_complete(test_band)
    print(f"   ✅ Ingestion: {result['status']}")

    rag = orch.query_rag("death metal band", n_results=2)
    print(f"   ✅ RAG: retrieved {len(rag['retrieved_documents'])} docs")

    orch.close()
except Exception as e:
    print(f"   ❌ Orchestrator Error: {e}")

print("\n" + "=" * 60)
print("LOCAL TEST COMPLETE")
print("=" * 60)