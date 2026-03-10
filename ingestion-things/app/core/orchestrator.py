"""
StorageOrchestrator — central hub for all RAG operations.

Responsibilities:
  1. Generate embeddings  (sentence-transformers, local)
  2. Store in Chroma      (semantic / vector search)
  3. Store in Neo4j       (graph relationships)
  4. RAG query            (retrieve → enrich → generate answer)
"""

from typing import List, Dict, Optional, Any, cast
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.clients.chroma import ChromaClientLocal
from app.clients.neo4j_client import Neo4jClient
from app.core.document_builder import DocumentBuilder

from sentence_transformers import SentenceTransformer


class StorageOrchestrator:

    def __init__(self):
        print("🎛️  Initialising Storage Orchestrator...")

        # ── databases ────────────────────────────────────────────────────────
        self.chroma = ChromaClientLocal()
        self.neo4j = Neo4jClient()

        # Document builder
        self.builder = DocumentBuilder()

        # Embedding model (local, runs on your M4 Mac)
        print("🧠 Loading embedding model...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        print("   ✅ Model loaded (384 dimensions)")

        # ── Chroma collection references ──────────────────────────────────────
        # Use the same collections ChromaClientLocal created
        self.collections = self.chroma.collections

        # ── optional LLM for answer generation ───────────────────────────────
        self._llm_available = self._init_llm()

        print("✅ Orchestrator ready")
        print(f"   Chroma collections: {list(self.collections.keys())}")
        print(f"   LLM generation: {'✅ enabled' if self._llm_available else '⚠️  disabled (no OPENAI_API_KEY)'}")

    # =========================================================================
    # LLM SETUP
    # =========================================================================

    def _init_llm(self) -> bool:
        """Try to load the openai client. Returns True if available."""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def generate_answer(self, question: str, context: str) -> str:
        """
        Send the context + question to an LLM and return a natural-language answer.
        Falls back to returning the raw context if no API key is configured.
        """
        if not self._llm_available:
            return (
                "⚠️  No LLM configured (add OPENAI_API_KEY to .env). "
                f"Here is the raw context:\n\n{context}"
            )

        import openai

        system_prompt = (
            "You are MetalMind, an expert on heavy metal music. "
            "Answer the user's question using ONLY the context provided. "
            "Be concise and factual. If the context doesn't contain enough information, say so."
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        try:
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"LLM error: {e}\n\nRaw context:\n{context}"

    # =========================================================================
    # INGESTION
    # =========================================================================

    def ingest_band_complete(self, band_data: Dict) -> Dict:
        """
        Full ingestion pipeline for a band.
          1. Build documents via DocumentBuilder
          2. Generate embeddings
          3. Upsert into Chroma collections
          4. Store graph nodes in Neo4j
        """
        result: Dict[str, Any] = {
            "band_name": band_data.get("name"),
            "status": "processing",
            "documents_created": 0,
            "chroma_ids": [],
            "neo4j_ids": [],
            "errors": [],
        }

        try:
            print(f"\n📦 Ingesting: {band_data['name']}")

            # ── 1. BUILD DOCUMENTS ───────────────────────────────────────────
            documents: List[tuple] = []

            band_doc = self.builder.build_band_document(band_data)
            documents.append(("bands", band_doc))

            for doc in self.builder.build_album_documents(band_data):
                documents.append(("albums", doc))

            for doc in self.builder.build_relationship_documents(band_data):
                documents.append(("members", doc))

            if band_data.get("reddit_posts"):
                for doc in self.builder.build_reddit_documents(
                    band_data["reddit_posts"], band_data["name"]
                ):
                    documents.append(("reddit", doc))

            result["documents_created"] = len(documents)

            # ── 2. EMBED & STORE IN CHROMA ───────────────────────────────────
            print(f"   📝 Embedding {len(documents)} documents...")

            for collection_name, doc in documents:
                embedding = self.embedder.encode(doc["text"]).tolist()

                self.collections[collection_name].upsert(
                    ids=[doc["id"]],
                    embeddings=[embedding],
                    documents=[doc["text"]],
                    metadatas=[self._sanitize_metadata(doc["metadata"])],
                )

                result["chroma_ids"].append({"collection": collection_name, "id": doc["id"]})

                if doc["type"] == "band":
                    band_data["chroma_doc_id"] = doc["id"]

            # ── 3. STORE IN NEO4J ────────────────────────────────────────────
            print("   🕸️  Building graph...")

            neo4j_band_id = self.neo4j.create_band(band_data)
            result["neo4j_ids"].append({"type": "band", "id": neo4j_band_id})

            for member in band_data.get("lineup", []):
                mid = self.neo4j.create_member(
                    band_data.get("mbid"),
                    {"name": member["name"], "role": member.get("role", "member")},
                )
                result["neo4j_ids"].append({"type": "member", "name": member["name"], "id": mid})

            for album in band_data.get("albums", []):
                aid = self.neo4j.create_album(band_data.get("mbid"), album)
                if aid:
                    result["neo4j_ids"].append({"type": "album", "title": album.get("title"), "id": aid})

            for genre in band_data.get("genres", []):
                self.neo4j.connect_genre(band_data.get("mbid"), genre)

            result["status"] = "success"
            print(f"   ✅ Done: {len(result['chroma_ids'])} vectors, "
                  f"{len(result['neo4j_ids'])} graph nodes")

        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            print(f"   ❌ Error: {e}")

        return result

    def ingest_multiple_bands(self, bands: List[Dict]) -> List[Dict]:
        """Ingest multiple bands with progress tracking."""
        results = []
        for i, band in enumerate(bands, 1):
            print(f"\n[{i}/{len(bands)}] {band['name']}")
            results.append(self.ingest_band_complete(band))

        successful = sum(1 for r in results if r["status"] == "success")
        print(f"\n📊 Ingestion complete: {successful}/{len(bands)} succeeded")
        return results

    # =========================================================================
    # RAG QUERY
    # =========================================================================

    def query_rag(self, question: str, n_results: int = 5) -> Dict:
        """
        Full RAG pipeline:
          1. Embed the question
          2. Search all Chroma collections
          3. Rank + deduplicate
          4. Enrich top results with Neo4j graph data
          5. Build context string
          6. Generate LLM answer (if key available)
        """
        print(f"\n🔮 RAG Query: '{question}'")

        query_embedding = self.embedder.encode(question).tolist()

        # ── search each collection ────────────────────────────────────────────
        all_results: List[Dict[str, Any]] = []

        for collection_name in ["bands", "albums", "members", "reddit"]:
            try:
                raw = self.collections[collection_name].query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"],
                )
                self._tag_source(raw, collection_name)
                all_results.extend(self._format_results(raw))
            except Exception:
                pass  # empty collection, skip

        # ── rank ─────────────────────────────────────────────────────────────
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top: List[Dict[str, Any]] = all_results[:n_results]

        # ── enrich with Neo4j ─────────────────────────────────────────────────
        enriched = self._enrich_with_graph(top)

        # ── build context ─────────────────────────────────────────────────────
        context = self._build_context(enriched)

        # ── generate answer ───────────────────────────────────────────────────
        answer = self.generate_answer(question, context)

        return {
            "question": question,
            "answer": answer,
            "retrieved_documents": enriched,
            "context": context,
            "sources": list(set(r["collection"] for r in enriched)),
        }

    # =========================================================================
    # DISCOVERY
    # =========================================================================

    def find_similar_bands(self, band_name: str, n: int = 5) -> List[Dict[str, Any]]:
        """Semantic similarity via Chroma, enriched with Neo4j graph data."""
        slug = self.builder._slugify(band_name)
        band_result = self.collections["bands"].get(
            ids=[slug], include=["embeddings", "metadatas"]
        )

        if band_result and band_result["ids"]:
            band_emb = band_result["embeddings"][0]
        else:
            band_emb = self.embedder.encode(f"band similar to {band_name}").tolist()

        results = self.collections["bands"].query(
            query_embeddings=[band_emb],
            n_results=n + 1,
        )
        formatted = self._format_results(results)
        formatted = [r for r in formatted if r["metadata"].get("name") != band_name]
        return self._enrich_with_graph(cast(List[Dict[str, Any]], formatted[:n]))

    def find_scene_bands(self, country: str, year_start: int, year_end: int) -> List[Dict[str, Any]]:
        """
        Graph-first: Neo4j filters by country/year → Chroma returns metadata.
        Falls back to in-memory filter if no graph data.
        """
        graph_bands = self.neo4j.get_scene_bands(country, year_start, year_end)

        results = []
        for band in graph_bands:
            band_name = band.get("band", "")
            try:
                res = self.collections["bands"].get(ids=[self.builder._slugify(band_name)])
                if res and res["ids"]:
                    results.append({
                        "name": band_name,
                        "metadata": res["metadatas"][0] if res["metadatas"] else {},
                        "albums_from_period": band.get("albums_from_period", []),
                    })
            except Exception:
                pass

        results.sort(key=lambda x: x["metadata"].get("popularity_score", 0), reverse=True)
        return results

    def get_stats(self) -> Dict:
        """Database document / node counts."""
        return {
            "chroma": self.chroma.get_stats(),
            "neo4j": {"bands": len(self.neo4j.get_all_bands()), "status": "connected"},
        }

    def close(self):
        self.neo4j.close()
        print("👋 Storage orchestrator closed")

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    def _sanitize_metadata(self, metadata: Dict) -> Dict[str, str | int | float | bool]:
        """Chroma only supports str/int/float/bool as metadata values."""
        sanitized: Dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                sanitized[key] = ", ".join(str(v) for v in value)
            elif value is None:
                sanitized[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized

    def _tag_source(self, results: Dict, source: str):
        """Tag Chroma result metadatas with the collection name."""
        if results.get("metadatas") and results["metadatas"][0]:
            for meta in results["metadatas"][0]:
                if meta:
                    meta["_source_collection"] = source

    def _format_results(self, chroma_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert raw Chroma query output to a list of clean dicts."""
        formatted: List[Dict[str, Any]] = []

        raw_ids: Any = chroma_results.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids or not raw_ids[0]:
            return formatted

        ids: List[Any] = raw_ids[0]
        raw_distances = chroma_results.get("distances")
        raw_documents = chroma_results.get("documents")
        raw_metadatas = chroma_results.get("metadatas")

        distances = cast(List[Any], raw_distances[0]) if raw_distances else []
        documents = cast(List[Any], raw_documents[0]) if raw_documents else []
        metadatas = cast(List[Any], raw_metadatas[0]) if raw_metadatas else []

        for i in range(len(ids)):
            score: float = float(1 - distances[i]) if i < len(distances) else 0.0
            text: str = str(documents[i]) if i < len(documents) else ""
            meta: Dict[str, Any] = dict(metadatas[i] or {}) if i < len(metadatas) else {}
            collection: str = str(meta.get("_source_collection", "unknown"))

            formatted.append({
                "id": ids[i],
                "score": score,
                "text": text,
                "metadata": meta,
                "collection": collection,
            })

        return formatted

    def _enrich_with_graph(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add Neo4j member and property data to Chroma search results."""
        enriched = []
        for result in results:
            meta = result.get("metadata", {})
            mbid = meta.get("mbid") or meta.get("band_mbid")

            if mbid:
                try:
                    graph_data = self.neo4j.find_band(mbid)
                    if graph_data:
                        result["graph_data"] = {
                            "members": self.neo4j.get_band_members(mbid),
                            "properties": graph_data,
                        }
                except Exception:
                    pass

            enriched.append(result)
        return enriched

    def _build_context(self, results: List[Dict[str, Any]]) -> str:
        """Build a text context block from retrieved documents for LLM input."""
        parts = []
        for i, result in enumerate(results, 1):
            meta = result.get("metadata", {})
            source = result.get("collection", "unknown")
            name = (
                meta.get("name") or meta.get("title")
                or meta.get("musician_name") or "Unknown"
            )
            text = result.get("text", "")[:300]
            parts.append(f"[{i}] {name} ({source}): {text}...")

            if result.get("graph_data"):
                members = result["graph_data"].get("members", [])[:3]
                if members:
                    names = [m["name"] for m in members]
                    parts.append(f"    Key members: {', '.join(names)}")

        return "\n\n".join(parts)


# ─── End-to-end smoke test ───────────────────────────────────────────────────
if __name__ == "__main__":
    orch = StorageOrchestrator()

    test_band: Dict[str, Any] = {
        "name": "Vildhjarta",
        "mbid": "test-vildhjarta-001",
        "genres": ["progressive death metal", "djent"],
        "country": "SE",
        "formed_year": 2004,
        "biography": "Swedish progressive metal band known for dark, complex compositions.",
        "albums": [
            {"title": "Måsstaden", "year": 2011, "type": "album"},
            {"title": "Måsstaden under vatten", "year": 2022, "type": "album"},
        ],
        "lineup": [
            {"name": "Daniel Bergström", "role": "vocals", "join_year": 2004},
            {"name": "Mattias Härd", "role": "guitar", "join_year": 2004},
        ],
        "reddit_mentions": 45,
    }

    result = orch.ingest_band_complete(test_band)
    print(f"\nIngestion: {result['status']}")

    rag = orch.query_rag("progressive death metal from Sweden", n_results=3)
    print(f"\nRAG retrieved {len(rag['retrieved_documents'])} documents")
    print(f"Answer: {rag['answer'][:300]}")

    orch.close()