"""FastAPI server for retrieval debugging.

Endpoints:
- POST /debug/search   — Debug search with full score decomposition
- POST /debug/compare  — A/B config comparison
- POST /debug/batch    — Run test suite with Recall@K metrics
- GET  /health         — Health check
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from debugger import RetrievalDebugger
from models import BatchTestRequest, CompareRequest, DebugSearchRequest
from test_suite import TestSuiteRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

debugger: RetrievalDebugger | None = None
runner: TestSuiteRunner | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global debugger, runner
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    debugger = RetrievalDebugger(qdrant_url=qdrant_url, embedding_model=embedding_model)
    runner = TestSuiteRunner(debugger)
    logger.info(f"Retrieval debugger initialized: qdrant={qdrant_url}")
    yield


app = FastAPI(
    title="POC-05: Retrieval Debugger",
    description="Test retrieval quality, compare configs, run regression suites",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "retrieval-debugger"}


@app.post("/debug/search")
async def debug_search(req: DebugSearchRequest):
    """Debug search with full score decomposition and timings."""
    try:
        result = await debugger.debug_search(
            query=req.query,
            kb_ids=req.kb_ids,
            top_k=req.top_k,
            final_k=req.final_k,
            similarity_threshold=req.similarity_threshold,
            dense_weight=req.dense_weight,
            sparse_weight=req.sparse_weight,
            rerank_model=req.rerank_model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/debug/compare")
async def compare_configs(req: CompareRequest):
    """Compare two retrieval configurations side-by-side."""
    try:
        result = await debugger.compare(
            query=req.query,
            kb_ids=req.kb_ids,
            config_a=req.config_a.model_dump(),
            config_b=req.config_b.model_dump(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@app.post("/debug/batch")
async def batch_test(req: BatchTestRequest):
    """Run a test suite and compute Recall@K metrics."""
    try:
        result = await runner.run(
            kb_ids=req.kb_ids,
            test_cases=[tc.model_dump() for tc in req.test_cases],
            top_k=req.top_k,
            final_k=req.final_k,
            dense_weight=req.dense_weight,
            sparse_weight=req.sparse_weight,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
