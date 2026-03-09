#!/usr/bin/env python3
"""
Local Integration Test
Tests all components without Docker
"""
import os
import sys
from dotenv import load_dotenv

# Project root (metalmind-ai/)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLIENTS = os.path.join(ROOT, "ingestion-things", "app", "clients")

sys.path.insert(0, CLIENTS)

load_dotenv(os.path.join(ROOT, ".env"))

print("=" * 60)
print("METALMIND LOCAL TEST")
print("=" * 60)

# Test 1: ChromaDB Local
print("\n1. Testing Local ChromaDB...")
try:
    from chroma import ChromaClientLocal
    chroma = ChromaClientLocal()
    print("   ✅ ChromaDB Local: OK")

    chroma.store_band({
        "name": "Test Band",
        "mbid": "test-456",
        "genres": ["death metal"],
        "country": "US",
        "formed_year": 1990
    }, [0.1] * 384)
    print("   ✅ Store band: OK")

except Exception as e:
    print(f"   ❌ ChromaDB Error: {e}")

# Test 2: Neo4j Local
print("\n2. Testing Local Neo4j...")
try:
    from neo4j_client import Neo4jClient
    neo4j = Neo4jClient()
    print("   ✅ Neo4j Local: OK")

    neo4j.create_band({
        "mbid": "test-789",
        "name": "Test Band Neo",
        "formed_year": 1985,
        "country": "UK",
        "genres": ["thrash metal"]
    })
    print("   ✅ Create band: OK")

    bands = neo4j.get_all_bands()
    print(f"   ✅ Query bands: Found {len(bands)} bands")

    neo4j.close()

except Exception as e:
    print(f"   ❌ Neo4j Error: {e}")

# Test 3: API Clients
print("\n3. Testing API Clients...")
try:
    from musicbrainz import MusicBrainzClient
    mb = MusicBrainzClient(user_agent="MetalMind/0.1.0 (antosw2000@gmail.com)")
    results = mb.search_artist("Metallica", limit=1)
    print(f"   ✅ MusicBrainz: Found {len(results)} artists")
except Exception as e:
    print(f"   ❌ MusicBrainz Error: {e}")

print("\n" + "=" * 60)
print("LOCAL TEST COMPLETE")
print("=" * 60)