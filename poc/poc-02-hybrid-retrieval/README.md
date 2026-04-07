# POC-02: Hybrid Retrieval Engine

## Feature
**Dense + Sparse vector search with configurable fusion, reranking, and threshold filtering**

This is the retrieval core of any RAG system. It implements RAGFlow's most battle-tested pattern: hybrid search that combines semantic understanding (vectors) with exact keyword matching (BM25).

## What Problem It Solves
- **Pure vector search** misses exact terminology (product codes, legal clauses, error codes)
- **Pure keyword search** misses semantic meaning ("car" doesn't match "automobile")
- **Fixed fusion weights** don't work across use cases (legal needs more keyword weight than general Q&A)
- Without **reranking**, initial recall quality limits final answer quality

## Key RAGFlow Patterns Implemented
- **Configurable fusion weights** (`rag/nlp/search.py` — `Dealer.search()`)
- **BM25 query construction** (`rag/nlp/query.py` — multi-field weighted search)
- **Three-tier ranking**: hybrid score → model reranking → threshold filtering
- **Token-aware context assembly** (`rag/prompts/generator.py` — `kb_prompt()`)
- **Fallback retry** with looser matching when results are empty

## Architecture

```
User Query
    │
    ├── Embed query → dense vector
    ├── Tokenize query → sparse vector (BM25)
    │
    ▼
Qdrant Hybrid Search
    ├── Dense: cosine similarity on "dense" vectors
    ├── Sparse: BM25 matching on "bm25" sparse vectors
    └── Fusion: RRF (Reciprocal Rank Fusion)
    │
    ▼
Optional: Cross-Encoder Reranking (Cohere/Jina)
    │
    ▼
Threshold Filtering (drop low-score chunks)
    │
    ▼
Token-Aware Context Assembly
    (Fit top chunks into LLM context window)
```

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server + CLI demo |
| `retriever.py` | Core hybrid retrieval logic with Qdrant |
| `reranker.py` | Cross-encoder reranking via litellm/Cohere |
| `context_builder.py` | Token-aware context window construction |
| `sparse_encoder.py` | Simple BM25 sparse vector generation |
| `config.py` | Retrieval configuration models |

## How to Run

```bash
# Prerequisites: Qdrant running + documents indexed via POC-01
docker run -p 6333:6333 qdrant/qdrant

# Set env vars
export OPENAI_API_KEY="sk-..."

# Run as API
uvicorn main:app --reload --port 8002

# Test retrieval:
# POST /search {"query": "fire safety", "kb_ids": ["my-kb"], "top_k": 10}
# POST /search/compare  — Compare different retrieval configs side-by-side
```

## How to Extend

1. **Add query expansion**: Use LLM to generate synonyms/rephrasings before search
2. **Add metadata filtering**: Filter by document type, date range, department
3. **Add query decomposition**: Split complex queries into sub-queries  
4. **Add caching**: Cache embeddings for repeated queries
5. **Wire to POC-03**: Feed retrieval results into citation-enforced generation
