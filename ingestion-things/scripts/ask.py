#!/usr/bin/env python3
import os
import sys

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.orchestrator import StorageOrchestrator

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/ask.py \"Your question here\"")
        print("Example: python3 scripts/ask.py \"What albums did Metallica release?\"")
        sys.exit(1)

    question = sys.argv[1]
    
    print("\n🎸 METALMIND RAG")
    print("=" * 60)
    
    # Load orchestrator (this connects safely to Chroma and Neo4j even if mass_ingest is running)
    orch = StorageOrchestrator()
    
    # Query!
    rag = orch.query_rag(question, n_results=5)
    
    print("\n" + "=" * 60)
    print(f"QUESTION: {question}")
    print("=" * 60)
    print(f"\n{rag['answer']}\n")
    print("-" * 60)
    print(f"Sources used: {', '.join(rag['sources']) if rag['sources'] else 'None'}")
    
    orch.close()

if __name__ == "__main__":
    main()
