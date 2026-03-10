from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.core.orchestrator import StorageOrchestrator
from app.core.collector import UnifiedCollector

app = FastAPI(
    title="MetalMind RAG API",
    description="Metal music knowledge graph + semantic search + LLM answers",
    version="0.2.0",
)

# ── singletons (initialised at startup) ──────────────────────────────────────
orchestrator: Optional[StorageOrchestrator] = None
collector: Optional[UnifiedCollector] = None


@app.on_event("startup")
async def startup():
    global orchestrator, collector
    orchestrator = StorageOrchestrator()
    collector = UnifiedCollector()


@app.on_event("shutdown")
async def shutdown():
    if orchestrator:
        orchestrator.close()


# =============================================================================
# INGESTION ENDPOINTS
# =============================================================================

class IngestRequest(BaseModel):
    band_name: str
    include_reddit: bool = True


@app.post("/ingest/band")
async def ingest_band(request: IngestRequest):
    """
    Full ingestion pipeline for a single band.
    Collects from MusicBrainz + Last.fm + Reddit, then stores in Chroma + Neo4j.
    """
    try:
        # Collect from all APIs (sync call, runs in the same thread)
        band_data = collector.collect(request.band_name)

        # Store in both databases
        result = orchestrator.ingest_band_complete(band_data)

        return {
            "status": result["status"],
            "band": band_data["name"],
            "genres": band_data.get("genres", []),
            "documents": result["documents_created"],
            "vectors_stored": len(result["chroma_ids"]),
            "graph_nodes": len(result["neo4j_ids"]),
            "errors": result.get("errors", []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/bulk")
async def ingest_bulk(band_names: List[str]):
    """
    Ingest multiple bands sequentially.
    For large lists consider running this as a background job.
    """
    results = []
    for name in band_names:
        try:
            band_data = collector.collect(name)
            result = orchestrator.ingest_band_complete(band_data)
            results.append({"band": name, "status": result["status"]})
        except Exception as e:
            results.append({"band": name, "status": "error", "error": str(e)})

    return {
        "total": len(band_names),
        "succeeded": sum(1 for r in results if r["status"] == "success"),
        "results": results,
    }


# =============================================================================
# RAG QUERY ENDPOINTS
# =============================================================================

class QueryRequest(BaseModel):
    question: str
    n_results: int = 5


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[str]
    retrieved_documents: List[dict]
    context: str


@app.post("/query", response_model=QueryResponse)
async def query_oracle(request: QueryRequest):
    """
    The Metal Oracle — ask anything about metal music.

    Examples:
      - "What are progressive death metal bands from Sweden?"
      - "Which bands are similar to Opeth?"
      - "Tell me about Vildhjarta"
    """
    try:
        rag = orchestrator.query_rag(request.question, request.n_results)
        return QueryResponse(
            question=rag["question"],
            answer=rag["answer"],
            sources=rag["sources"],
            retrieved_documents=rag["retrieved_documents"],
            context=rag["context"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# DISCOVERY ENDPOINTS
# =============================================================================

@app.get("/discover/similar/{band_name}")
async def discover_similar(band_name: str, n: int = 5):
    """Find bands semantically similar to the given band (Chroma + Neo4j enrichment)."""
    try:
        similar = orchestrator.find_similar_bands(band_name, n)
        return {
            "reference_band": band_name,
            "similar_bands": [
                {
                    "name": s["metadata"].get("name"),
                    "genres": s["metadata"].get("genres"),
                    "country": s["metadata"].get("country"),
                    "similarity_score": round(s["score"], 4),
                    "members": s.get("graph_data", {}).get("members", [])[:3],
                }
                for s in similar
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/discover/scene")
async def discover_scene(country: str, year_start: int, year_end: int):
    """Discover bands from a specific country and time period (Neo4j + Chroma)."""
    try:
        bands = orchestrator.find_scene_bands(country, year_start, year_end)
        return {
            "scene": f"{country} {year_start}–{year_end}",
            "band_count": len(bands),
            "bands": bands[:20],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STATS & HEALTH
# =============================================================================

@app.get("/stats")
async def get_stats():
    """Database document and node counts."""
    return orchestrator.get_stats()


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "rag_ready": orchestrator is not None,
        "llm_enabled": orchestrator._llm_available if orchestrator else False,
    }


@app.get("/")
async def root():
    return {
        "service": "MetalMind RAG API",
        "version": "0.2.0",
        "docs": "/docs",
    }