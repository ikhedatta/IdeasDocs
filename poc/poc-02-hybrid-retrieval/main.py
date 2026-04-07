"""FastAPI server + CLI for hybrid retrieval.

Endpoints:
- POST /search           — Hybrid search with score breakdown
- POST /search/context   — Search + LLM-ready context assembly
- POST /search/compare   — Compare two retrieval configs side-by-side
- GET  /health           — Health check
"""
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import FusionMethod, RetrievalConfig
from retriever import HybridRetriever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Pydantic request/response models ---


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    kb_ids: list[str] = Field(..., min_length=1)
    top_k: int = Field(default=20, ge=1, le=100)
    final_k: int = Field(default=5, ge=1, le=50)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    dense_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    sparse_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    fusion_method: str = Field(default="rrf")
    rerank_model: str | None = Field(default=None)
    max_context_tokens: int = Field(default=4096, ge=256, le=128000)


class CompareRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    kb_ids: list[str] = Field(..., min_length=1)
    config_a: SearchRequest
    config_b: SearchRequest


def _to_config(req: SearchRequest) -> RetrievalConfig:
    return RetrievalConfig(
        top_k=req.top_k,
        final_k=req.final_k,
        similarity_threshold=req.similarity_threshold,
        dense_weight=req.dense_weight,
        sparse_weight=req.sparse_weight,
        fusion_method=FusionMethod(req.fusion_method),
        rerank_model=req.rerank_model,
        max_context_tokens=req.max_context_tokens,
    )


# --- App ---

retriever: HybridRetriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global retriever
    import os
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    retriever = HybridRetriever(qdrant_url=qdrant_url, embedding_model=embedding_model)
    logger.info(f"Retriever initialized: qdrant={qdrant_url}, model={embedding_model}")
    yield


app = FastAPI(
    title="POC-02: Hybrid Retrieval Engine",
    description="Dense + sparse hybrid search with configurable fusion and reranking",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hybrid-retrieval"}


@app.post("/search")
async def search(req: SearchRequest):
    """Hybrid search with full score breakdown."""
    config = _to_config(req)
    try:
        results = await retriever.search(req.query, req.kb_ids, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "query": req.query,
        "config": {
            "fusion_method": config.fusion_method.value,
            "dense_weight": config.dense_weight,
            "sparse_weight": config.sparse_weight,
            "top_k": config.top_k,
            "final_k": config.final_k,
            "threshold": config.similarity_threshold,
            "rerank_model": config.rerank_model,
        },
        "result_count": len(results),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "content": r.content,
                "document_name": r.document_name,
                "document_id": r.document_id,
                "chunk_order": r.chunk_order,
                "scores": r.score_breakdown(),
            }
            for r in results
        ],
    }


@app.post("/search/context")
async def search_with_context(req: SearchRequest):
    """Search and build LLM-ready context with token budget."""
    config = _to_config(req)
    try:
        result = await retriever.search_with_context(req.query, req.kb_ids, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/search/compare")
async def compare_configs(req: CompareRequest):
    """Compare two retrieval configurations side-by-side.

    Useful for tuning: run the same query with different weights,
    fusion methods, or reranker models and see the differences.
    """
    config_a = _to_config(req.config_a)
    config_b = _to_config(req.config_b)

    try:
        results_a = await retriever.search(req.query, req.kb_ids, config_a)
        results_b = await retriever.search(req.query, req.kb_ids, config_b)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    ids_a = {r.chunk_id for r in results_a}
    ids_b = {r.chunk_id for r in results_b}

    return {
        "query": req.query,
        "config_a": {
            "results": len(results_a),
            "top_scores": [r.score_breakdown() for r in results_a[:5]],
        },
        "config_b": {
            "results": len(results_b),
            "top_scores": [r.score_breakdown() for r in results_b[:5]],
        },
        "overlap": {
            "shared_chunks": len(ids_a & ids_b),
            "only_in_a": len(ids_a - ids_b),
            "only_in_b": len(ids_b - ids_a),
            "jaccard_similarity": (
                len(ids_a & ids_b) / len(ids_a | ids_b) if ids_a | ids_b else 0.0
            ),
        },
    }


# --- CLI ---


def cli_search():
    """Run a search from the command line."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Hybrid retrieval search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--kb-ids", nargs="+", required=True, help="Knowledge base IDs")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument("--dense-weight", type=float, default=0.7)
    parser.add_argument("--sparse-weight", type=float, default=0.3)
    parser.add_argument("--threshold", type=float, default=0.2)
    parser.add_argument("--rerank-model", type=str, default=None)
    parser.add_argument("--fusion", choices=["rrf", "weighted_sum"], default="rrf")
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--embedding-model", default=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    args = parser.parse_args()

    config = RetrievalConfig(
        top_k=args.top_k,
        final_k=args.final_k,
        similarity_threshold=args.threshold,
        dense_weight=args.dense_weight,
        sparse_weight=args.sparse_weight,
        fusion_method=FusionMethod(args.fusion),
        rerank_model=args.rerank_model,
    )

    ret = HybridRetriever(qdrant_url=args.qdrant_url, embedding_model=args.embedding_model)
    results = asyncio.run(ret.search(args.query, args.kb_ids, config))

    print(f"\n{'='*60}")
    print(f"Query: {args.query}")
    print(f"Config: fusion={args.fusion} dense={args.dense_weight} sparse={args.sparse_weight}")
    print(f"Results: {len(results)}")
    print(f"{'='*60}\n")

    for i, r in enumerate(results, 1):
        scores = r.score_breakdown()
        print(f"[{i}] Score: {scores['final']:.4f} (dense={scores['dense']}, sparse={scores['sparse']})")
        print(f"    Doc: {r.document_name} | Chunk: {r.chunk_order}")
        preview = r.content[:150].replace("\n", " ")
        print(f"    {preview}...")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "serve":
        cli_search()
    else:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
