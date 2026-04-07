"""FastAPI server + CLI for citation-enforced RAG.

Endpoints:
- POST /ask          — Ask a question, get cited answer
- POST /ask/stream   — Streaming version (SSE)
- POST /ask/debug    — Full debug output with all intermediate steps
- GET  /health       — Health check
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from llm_client import LLMClient
from rag_pipeline import RAGConfig, RAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# --- Request/Response models ---


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    kb_ids: list[str] = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    final_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    llm_model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    prompt_template: str = Field(default="default")


def _to_config(req: AskRequest) -> RAGConfig:
    return RAGConfig(
        top_k=req.top_k,
        final_k=req.final_k,
        similarity_threshold=req.similarity_threshold,
        llm_model=req.llm_model,
        temperature=req.temperature,
        prompt_template=req.prompt_template,
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )


# --- App ---

pipeline: RAGPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    config = RAGConfig(
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    )
    pipeline = RAGPipeline(qdrant_url=qdrant_url, config=config)
    logger.info(f"RAG pipeline initialized: qdrant={qdrant_url}, llm={config.llm_model}")
    yield


app = FastAPI(
    title="POC-03: Citation-Enforced RAG",
    description="Retrieve, generate, and cite — grounded answers only",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "citation-rag"}


@app.post("/ask")
async def ask(req: AskRequest):
    """Ask a question and get a cited answer."""
    config = _to_config(req)
    try:
        response = await pipeline.ask(req.question, req.kb_ids, config)
    except Exception as e:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail=str(e))

    return response.to_dict()


@app.post("/ask/debug")
async def ask_debug(req: AskRequest):
    """Full debug mode — returns all intermediate data."""
    config = _to_config(req)
    try:
        response = await pipeline.ask(req.question, req.kb_ids, config)
    except Exception as e:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail=str(e))

    result = response.to_dict()
    # Add full source chunks in debug mode
    result["source_chunks_full"] = response.source_chunks
    result["config_used"] = {
        "top_k": config.top_k,
        "final_k": config.final_k,
        "similarity_threshold": config.similarity_threshold,
        "llm_model": config.llm_model,
        "temperature": config.temperature,
        "prompt_template": config.prompt_template,
        "embedding_model": config.embedding_model,
    }
    return result


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """Streaming answer via Server-Sent Events.

    The final event includes citations and metadata.
    """
    config = _to_config(req)

    async def event_stream():
        try:
            # First retrieve chunks (non-streaming)
            response = await pipeline.ask(req.question, req.kb_ids, config)

            # Stream the answer
            yield f"data: {json.dumps({'type': 'answer', 'content': response.answer})}\n\n"

            # Then send citations
            yield f"data: {json.dumps({'type': 'citations', 'content': response.citations})}\n\n"

            # Send metadata
            yield f"data: {json.dumps({'type': 'metadata', 'content': {'confidence': response.confidence, 'citation_coverage': response.citation_coverage, 'timings_ms': response.timings_ms}})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- CLI ---


def cli_ask():
    """Ask a question from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Citation-enforced RAG")
    parser.add_argument("question", help="Question to ask")
    parser.add_argument("--kb-ids", nargs="+", required=True, help="Knowledge base IDs")
    parser.add_argument("--llm-model", default=os.getenv("LLM_MODEL", "gpt-4o-mini"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument("--template", choices=["default", "strict", "conversational"], default="default")
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    args = parser.parse_args()

    config = RAGConfig(
        llm_model=args.llm_model,
        top_k=args.top_k,
        final_k=args.final_k,
        prompt_template=args.template,
    )

    p = RAGPipeline(qdrant_url=args.qdrant_url, config=config)
    response = asyncio.run(p.ask(args.question, args.kb_ids, config))

    print(f"\n{'='*60}")
    print(f"Question: {args.question}")
    print(f"Confidence: {response.confidence}")
    print(f"Citation Coverage: {response.citation_coverage:.0%}")
    print(f"{'='*60}\n")
    print(response.answer)
    print(f"\n{'─'*60}")
    print("Citations:")
    for c in response.citations:
        print(f"  [{c['index']}] {c['document_name']} (score: {c['score']})")
        print(f"      {c['content_preview']}")
    print(f"\nTimings: {response.timings_ms}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "serve":
        cli_ask()
    else:
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
