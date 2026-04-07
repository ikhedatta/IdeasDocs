# POC-05: Retrieval Debugger

## Feature
**Test retrieval without LLM, score decomposition, latency timing, A/B config comparison**

The hardest bug to fix in a RAG system is "why did it return the wrong answer?" This POC implements RAGFlow's `/chunk/retrieval_test` pattern — a dedicated tool to inspect retrieval quality without the LLM layer.

## What Problem It Solves
- **Opaque retrieval**: Users can't see why certain chunks rank higher than others
- **Tuning is blind**: Without per-step scores, adjusting weights is guesswork
- **No baseline comparison**: How do you know `dense_weight=0.7` is better than `0.5`?
- **Latency debugging**: Is slowness in embedding, search, or reranking?
- **Regression testing**: After reindexing, does retrieval quality hold?

## Key RAGFlow Patterns Implemented
- **Retrieval test endpoint** (`chunk_app.py` — `/retrieval_test`)
- **Score decomposition** (dense, sparse, combined, rerank, final)
- **Per-step timing** (embed, search, rerank, context assembly)
- **A/B comparison** (same query, two configs, overlap analysis)
- **Test suite runner** (batch queries against golden answers)

## Architecture

```
Debugger Input
    │
    ├── Single query test
    ├── A/B config comparison
    └── Batch test suite
    │
    ▼
Retrieval Pipeline (from POC-02)
    │
    ▼
Debug Output
    ├── Per-chunk scores: dense, sparse, combined, rerank, final
    ├── Per-step timings: embed_ms, search_ms, rerank_ms
    ├── Rank position tracking
    ├── Overlap analysis (A vs B)
    └── Recall@K against golden set
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server with debug endpoints |
| `debugger.py` | Core debug retrieval with full tracing |
| `test_suite.py` | Batch test runner with Recall@K metrics |
| `models.py` | Request/response models |

## How to Run

```bash
export OPENAI_API_KEY="sk-..."

uvicorn main:app --reload --port 8005

# Test retrieval:
# POST /debug/search {"query": "...", "kb_ids": [...]}
# POST /debug/compare  — A/B comparison
# POST /debug/batch    — Run test suite
```

## How to Extend

1. **Golden test sets**: Import/export test suites for CI integration
2. **NDCG/MRR metrics**: Add more IR metrics beyond Recall@K
3. **Visual dashboard**: Connect to React frontend for interactive tuning
4. **Automated tuning**: Grid search over weight combinations
5. **Regression alerts**: Flag when retrieval quality drops below threshold
