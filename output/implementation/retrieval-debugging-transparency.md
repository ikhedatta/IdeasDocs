# Implementation Plan: Retrieval Debugging & Transparency

## Priority Focus Feature — Deep Dive

---

## 1. How RAGFlow Does It

### Retrieval Testing

**File**: `api/apps/chunk_app.py` — `POST /chunk/retrieval_test`

RAGFlow provides a dedicated endpoint that runs retrieval WITHOUT LLM generation:

```python
# Simplified from actual implementation
@manager.route("/retrieval_test", methods=["POST"])
@login_required
async def retrieval_test():
    kb_ids = request.json["kb_ids"]
    question = request.json["question"]
    similarity_threshold = request.json.get("similarity_threshold", 0.2)
    vector_similarity_weight = request.json.get("vector_similarity_weight", 0.3)
    top_k = request.json.get("top_k", 1024)
    
    # Load embedding model
    embd_mdl = EmbeddingModel[factory](api_key, model_name, base_url)
    
    # Run search (same code path as chat, but no LLM)
    ranks = Dealer.search(question, embd_mdl, kb_ids, ...)
    
    # Return scored chunks
    return [
        {
            "chunk_id": chunk.id,
            "content": chunk.text,
            "document_name": chunk.doc_name,
            "similarity": chunk.score,
            "vector_similarity": chunk.vector_score,
            "term_similarity": chunk.term_score,
            "positions": chunk.positions,
            "image_id": chunk.img_id,
        }
        for chunk in ranks
    ]
```

### Scoring Visibility

The `Dealer.rerank()` method computes scores with individual components:

```python
# From rag/nlp/search.py
def rerank(query_tokens, chunks, vector_similarity_weight, ...):
    for chunk in chunks:
        # Token similarity (BM25-like)
        tk_sim = token_similarity(query_tokens, chunk.tokens)
        
        # Vector similarity (cosine)
        vt_sim = chunk.vector_score
        
        # Combined score
        score = tkweight * tk_sim + vtweight * vt_sim
        
        # Boost factors
        score += pagerank_boost
        score += tag_feature_score
```

### Chunk Source Tracing

Each chunk includes `positions` — JSON-encoded PDF page coordinates:
```json
[[page_num, x1, y1, x2, y2], [page_num, x1, y1, x2, y2]]
```

This enables the frontend to highlight the exact source region in the PDF viewer.

### Chat Response References

The chat response includes a `reference` object:
```python
{
    "chunks": [
        {
            "chunk_id": "abc123",
            "content_with_weight": "...",
            "doc_name": "Safety_Guide.pdf",
            "doc_id": "doc456",
            "positions": [[3, 100, 200, 500, 300]],
            "similarity": 0.94,
            "vector_similarity": 0.95,
            "term_similarity": 0.82,
            "image_id": "img789",
        }
    ],
    "doc_aggs": [
        {"doc_name": "Safety_Guide.pdf", "doc_id": "doc456", "count": 3}
    ]
}
```

---

## 2. What's Missing in RAGFlow

1. **No query decomposition visibility**: Can't see how multi-turn refinement changed the query
2. **No embedding visualization**: Can't see the query vector or chunk vectors
3. **No latency breakdown**: No timing for embedding, search, rerank stages
4. **No A/B comparison**: Can't compare different retrieval configs side-by-side
5. **No historical query logging**: Can't review past retrieval performance
6. **No relevance feedback loop**: No easy way to mark "this chunk is relevant/irrelevant"

---

## 3. Implementation Plan for Our System

### 3.1 Retrieval Debug API

```python
# routers/retrieval_debug.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from uuid import UUID
from typing import Optional
import time

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval-debug"])

class RetrievalTestRequest(BaseModel):
    query: str
    kb_ids: list[UUID]
    vector_weight: float = 0.8
    similarity_threshold: float = 0.2
    top_k: int = 20
    rerank_model: Optional[str] = None
    include_inactive: bool = False
    metadata_filter: Optional[dict] = None

class ScoredChunk(BaseModel):
    chunk_id: str
    content: str
    document_id: str
    document_name: str
    
    # Individual score components
    dense_score: float        # Cosine similarity
    sparse_score: float       # BM25 score
    combined_score: float     # Fusion score
    rerank_score: Optional[float] = None  # Cross-encoder score
    final_score: float        # After all adjustments
    
    # Source info
    source_pages: list[int]
    chunk_order: int
    metadata: dict
    tags: list[str]
    is_active: bool

class RetrievalTestResponse(BaseModel):
    # Request info
    query: str
    refined_query: Optional[str] = None  # After multi-turn refinement
    query_tokens: list[str]  # Tokenized query (for BM25 debug)
    
    # Results
    chunks: list[ScoredChunk]
    total_candidates: int  # Before threshold filtering
    
    # Timing
    embedding_latency_ms: float
    search_latency_ms: float
    rerank_latency_ms: float
    total_latency_ms: float
    
    # Config used
    vector_weight: float
    similarity_threshold: float
    rerank_model: Optional[str]

@router.post("/test")
async def test_retrieval(
    body: RetrievalTestRequest,
    retrieval_service: RetrievalService = Depends(),
) -> RetrievalTestResponse:
    """Test retrieval without LLM generation. Returns scored chunks with timing."""
    
    start = time.perf_counter()
    
    # Step 1: Embed query
    t0 = time.perf_counter()
    query_vector = await retrieval_service.embed_query(body.query)
    embedding_ms = (time.perf_counter() - t0) * 1000
    
    # Step 2: Tokenize for BM25
    query_tokens = retrieval_service.tokenize_query(body.query)
    
    # Step 3: Search
    t0 = time.perf_counter()
    raw_results = await retrieval_service.hybrid_search(
        query_vector=query_vector,
        query_tokens=query_tokens,
        kb_ids=body.kb_ids,
        top_k=body.top_k,
        vector_weight=body.vector_weight,
        metadata_filter=body.metadata_filter,
        include_inactive=body.include_inactive,
    )
    search_ms = (time.perf_counter() - t0) * 1000
    
    # Step 4: Rerank (optional)
    rerank_ms = 0
    if body.rerank_model:
        t0 = time.perf_counter()
        raw_results = await retrieval_service.rerank(
            query=body.query,
            chunks=raw_results,
            model=body.rerank_model,
        )
        rerank_ms = (time.perf_counter() - t0) * 1000
    
    # Step 5: Filter by threshold
    total_candidates = len(raw_results)
    filtered = [r for r in raw_results if r.final_score >= body.similarity_threshold]
    
    total_ms = (time.perf_counter() - start) * 1000
    
    return RetrievalTestResponse(
        query=body.query,
        query_tokens=query_tokens,
        chunks=[ScoredChunk(**r.dict()) for r in filtered],
        total_candidates=total_candidates,
        embedding_latency_ms=round(embedding_ms, 1),
        search_latency_ms=round(search_ms, 1),
        rerank_latency_ms=round(rerank_ms, 1),
        total_latency_ms=round(total_ms, 1),
        vector_weight=body.vector_weight,
        similarity_threshold=body.similarity_threshold,
        rerank_model=body.rerank_model,
    )


class CompareRequest(BaseModel):
    query: str
    kb_ids: list[UUID]
    configs: list[dict]  # Each dict has {vector_weight, threshold, rerank_model, ...}

class CompareResponse(BaseModel):
    query: str
    results: list[RetrievalTestResponse]  # One per config

@router.post("/compare")
async def compare_configs(
    body: CompareRequest,
    retrieval_service: RetrievalService = Depends(),
) -> CompareResponse:
    """Compare multiple retrieval configurations side-by-side."""
    results = []
    for config in body.configs:
        result = await test_retrieval(
            RetrievalTestRequest(query=body.query, kb_ids=body.kb_ids, **config),
            retrieval_service,
        )
        results.append(result)
    return CompareResponse(query=body.query, results=results)
```

### 3.2 Retrieval Trace Logging

```python
# services/retrieval_trace.py
from dataclasses import dataclass, asdict
from datetime import datetime
from uuid import uuid4
import json

@dataclass
class RetrievalTrace:
    """Complete trace of a retrieval operation for debugging and analytics."""
    trace_id: str
    timestamp: datetime
    
    # Input
    original_query: str
    refined_query: str | None
    conversation_id: str | None
    
    # Search config
    kb_ids: list[str]
    vector_weight: float
    similarity_threshold: float
    rerank_model: str | None
    
    # Results
    total_candidates: int
    chunks_after_threshold: int
    chunks_after_rerank: int
    final_chunk_count: int
    
    # Scores
    top_score: float
    avg_score: float
    min_score: float
    score_distribution: list[float]  # Histogram bins
    
    # Timing
    embedding_ms: float
    search_ms: float
    rerank_ms: float
    total_ms: float
    
    # Quality signals (filled later)
    user_feedback: str | None = None  # thumbs_up, thumbs_down
    cited_chunk_ids: list[str] | None = None

class RetrievalTraceService:
    """Log and query retrieval traces for debugging and optimization."""
    
    async def log_trace(self, trace: RetrievalTrace):
        """Store trace in PostgreSQL for analysis."""
        await TraceRepository.create(**asdict(trace))
    
    async def get_traces(
        self,
        kb_id: str | None = None,
        time_range: tuple[datetime, datetime] | None = None,
        min_latency_ms: float | None = None,
        max_score_below: float | None = None,
        limit: int = 100,
    ) -> list[RetrievalTrace]:
        """Query traces with flexible filtering for debugging."""
        ...
    
    async def get_analytics(self, kb_id: str, days: int = 7) -> dict:
        """Aggregate analytics for a time period."""
        return {
            "total_queries": 1234,
            "avg_latency_ms": 45.2,
            "p95_latency_ms": 120.0,
            "avg_chunks_retrieved": 8.3,
            "avg_top_score": 0.82,
            "low_score_queries": 23,  # top_score < 0.5
            "zero_result_queries": 5,
            "feedback_positive_rate": 0.87,
        }
```

### 3.3 Relevance Feedback System

```python
# routers/feedback.py

class FeedbackRequest(BaseModel):
    conversation_id: UUID
    message_id: UUID
    feedback_type: str  # thumbs_up, thumbs_down
    # Optional: per-chunk relevance
    chunk_feedback: Optional[list[dict]] = None
    # [{"chunk_id": "abc", "is_relevant": true}, ...]

@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest):
    """Submit user feedback on a response. Used for retrieval quality tracking."""
    # Store feedback
    await FeedbackService.create(body)
    
    # Link to retrieval trace
    trace = await RetrievalTraceService.get_by_conversation(body.conversation_id)
    if trace:
        await RetrievalTraceService.update_feedback(
            trace.trace_id, body.feedback_type
        )
    
    # Per-chunk feedback for fine-tuning retrieval
    if body.chunk_feedback:
        for cf in body.chunk_feedback:
            await ChunkFeedbackService.log(
                chunk_id=cf["chunk_id"],
                query=trace.original_query if trace else None,
                is_relevant=cf["is_relevant"],
            )
```

### 3.4 UI Implementation

#### Retrieval Debug Panel

```
┌─────────────────────────────────────────────────────────────┐
│  🔬 Retrieval Debugger                                      │
│                                                             │
│  Query: [What are the fire safety requirements?       ] [⚡] │
│                                                             │
│  ┌── Config ─────────────────────────────────────────────┐  │
│  │ KBs: [✓ Technical] [✓ Safety] [  HR  ]              │  │
│  │ Vector Weight: [====●=====] 0.80                      │  │
│  │ Threshold:     [==●=======] 0.20                      │  │
│  │ Reranker:      [Cohere Rerank v3.5 ▾]                │  │
│  │ Top K:         [20   ]                                │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌── Timing ─────────────────────────────────────────────┐  │
│  │ Embed: 12ms │ Search: 34ms │ Rerank: 89ms │ Total: 135ms│
│  │ Candidates: 156 → Threshold: 18 → Final: 18           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌── Score Distribution ──────────────────────────────────┐ │
│  │  0.9-1.0  ██ 2                                        │ │
│  │  0.8-0.9  ████ 4                                      │ │
│  │  0.7-0.8  ██████ 6                                    │ │
│  │  0.6-0.7  ████ 4                                      │ │
│  │  0.5-0.6  ██ 2                                        │ │
│  │  < 0.5    --- (filtered)                              │ │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌── Results ────────────────────────────────────────────┐  │
│  │ #1 │ Safety_Guide.pdf, Chunk 12      │ Score: 0.94   │  │
│  │    │ Dense: 0.95 │ Sparse: 0.82 │ Rerank: 0.97      │  │
│  │    │ "Fire evacuation procedures must be posted..."   │  │
│  │    │ [👍 Relevant] [👎 Not relevant] [View in Doc]    │  │
│  │ ─────────────────────────────────────────────────────│  │
│  │ #2 │ Safety_Guide.pdf, Chunk 15      │ Score: 0.88   │  │
│  │    │ Dense: 0.89 │ Sparse: 0.75 │ Rerank: 0.91      │  │
│  │    │ "Fire extinguisher locations include..."         │  │
│  │    │ [👍 Relevant] [👎 Not relevant] [View in Doc]    │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### A/B Config Comparison View

```
┌─────────────────────────────────────────────────────────────┐
│  🔬 Config Comparison: "fire safety requirements"           │
│                                                             │
│  ┌── Config A ─────────────┐  ┌── Config B ─────────────┐  │
│  │ Weight: 0.8 vector      │  │ Weight: 0.5 vector      │  │
│  │ Reranker: None          │  │ Reranker: Cohere v3.5   │  │
│  │ Time: 46ms              │  │ Time: 135ms             │  │
│  │ Results: 18             │  │ Results: 15             │  │
│  ├──────────────────────────┤  ├──────────────────────────┤  │
│  │ #1 Chunk 12 (0.94) ✓   │  │ #1 Chunk 12 (0.97) ✓   │  │
│  │ #2 Chunk 15 (0.88) ✓   │  │ #2 Chunk 8  (0.93) NEW │  │
│  │ #3 Chunk 8  (0.82)     │  │ #3 Chunk 15 (0.91) ✓   │  │
│  │ #4 Chunk 3  (0.76)     │  │ #4 Chunk 22 (0.85) NEW │  │
│  │ #5 Chunk 22 (0.71)     │  │ #5 Chunk 3  (0.79)     │  │
│  └──────────────────────────┘  └──────────────────────────┘  │
│                                                             │
│  Overlap: 14/18 chunks shared (78%)                         │
│  Config B reranked Chunk 8 from #3 to #2 (likely better)    │
└─────────────────────────────────────────────────────────────┘
```

#### Chat Response with Source Tracing

```
┌─────────────────────────────────────────────────────────────┐
│  Chat: Safety Assistant                                     │
│                                                             │
│  You: What are the fire safety requirements?                │
│                                                             │
│  Assistant:                                                 │
│  Fire evacuation procedures must be posted in all           │
│  common areas [Source:1]. All personnel must complete        │
│  fire safety training within 30 days of hire [Source:2].    │
│  Fire extinguishers must be inspected monthly and are       │
│  located at every emergency exit [Source:3].                │
│                                                             │
│  ┌── Sources ───────────────────────────────────────────┐   │
│  │ [1] Safety_Guide.pdf, p.12     Score: 0.94          │   │
│  │     "Fire evacuation procedures must be posted..."   │   │
│  │     [View Chunk] [View in PDF]                       │   │
│  │                                                      │   │
│  │ [2] Safety_Guide.pdf, p.3      Score: 0.88          │   │
│  │     "All personnel must complete safety training..." │   │
│  │     [View Chunk] [View in PDF]                       │   │
│  │                                                      │   │
│  │ [3] Safety_Guide.pdf, p.15     Score: 0.82          │   │
│  │     "Fire extinguisher locations include..."         │   │
│  │     [View Chunk] [View in PDF]                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  [👍] [👎] [🔍 Debug Retrieval]                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.5 Retrieval Quality Dashboard

```python
# routers/retrieval_analytics.py

@router.get("/analytics/retrieval")
async def retrieval_analytics(
    kb_id: Optional[UUID] = None,
    days: int = 7,
) -> RetrievalAnalyticsResponse:
    """Dashboard data for retrieval quality monitoring."""
    return {
        "period": f"Last {days} days",
        "total_queries": 4523,
        "avg_latency_ms": 78,
        "p50_latency_ms": 45,
        "p95_latency_ms": 220,
        "p99_latency_ms": 890,
        "avg_chunks_retrieved": 8.3,
        "avg_top_score": 0.82,
        "queries_with_zero_results": 23,
        "queries_below_threshold": 156,
        "feedback_positive_rate": 0.87,
        "most_common_queries": [
            {"query": "fire safety requirements", "count": 45, "avg_score": 0.91},
            {"query": "onboarding process", "count": 38, "avg_score": 0.85},
        ],
        "low_score_queries": [
            {"query": "vacation policy exceptions", "count": 12, "avg_score": 0.31},
            {"query": "remote work equipment reimbursement", "count": 8, "avg_score": 0.28},
        ],
        "latency_trend": [
            {"date": "2024-03-01", "p50": 42, "p95": 180},
            {"date": "2024-03-02", "p50": 45, "p95": 200},
            # ...
        ],
    }
```

### 3.6 Improvements Over RAGFlow

1. **Individual Score Components**: RAGFlow returns a single combined score. We return dense, sparse, rerank, and final scores separately — essential for debugging.

2. **Latency Breakdown**: RAGFlow has no timing. We measure embed, search, and rerank stages independently.

3. **A/B Comparison**: Compare different retrieval configurations side-by-side. RAGFlow has no comparison capability.

4. **Relevance Feedback**: Per-chunk relevance marking. RAGFlow only has conversation-level thumbs up/down.

5. **Retrieval Analytics Dashboard**: Aggregate quality metrics over time. RAGFlow has no analytics.

6. **Query History**: All retrieval operations are traced and queryable. RAGFlow doesn't log retrieval details.

7. **Score Distribution Visualization**: Histogram of chunk scores helps identify whether the KB has relevant content for a query type.
