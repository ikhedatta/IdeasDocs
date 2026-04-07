# 3. Retrieval & Ranking Strategy — Deep Analysis

## Overview

RAGFlow implements a **three-tier retrieval and ranking system**: hybrid search → configurable reranking → token-aware context construction. This is the most production-ready part of the codebase.

---

## 3.1 Vector Search Approach

### Implementation

**File**: `common/doc_store/es_conn.py` (Elasticsearch), `common/doc_store/infinity_conn.py` (Infinity)

RAGFlow uses Elasticsearch's `knn` search with cosine similarity:

```python
MatchDenseExpr(
    vector_field="q_768_vec",      # or q_1024_vec depending on embedding model
    query_vector=[0.12, -0.34, ...],  # query embedding
    similarity=0.1,                 # minimum threshold
    topn=1024                       # max candidates
)
```

**Embedding Models Supported**:
- BGE-M3 (768-dim, default) — multilingual
- OpenAI text-embedding-3-small/large (1536/3072-dim)
- Cohere embed-v3 (1024-dim)
- Jina embeddings (768-dim)
- Local models via HuggingFace/Ollama

**Key Design Decision**: The embedding dimension is part of the field name (`q_768_vec`, `q_1024_vec`). This means switching embedding models requires re-indexing all chunks. RAGFlow handles this at the KB level — each KB is locked to one embedding model.

### Our Adaptation for Qdrant

Qdrant natively handles vector search with cosine similarity. Key advantages:
- Named vectors (can store multiple embeddings per point)
- Payload indexing for filtering
- Quantization for memory efficiency
- No need for field-name dimension encoding

---

## 3.2 Hybrid Search Implementation

### BM25 Component

**File**: `rag/nlp/query.py` — `FulltextQueryer`

This is surprisingly sophisticated:

1. **Tokenization**: Uses `rag_tokenizer` for fine-grained Chinese/English tokenization
2. **Synonym Expansion**: Adds synonyms with reduced weight
3. **Bigram Generation**: Adjacent token pairs for phrase matching
4. **Multi-field Search**: Queries 7 fields with different weights:
   - `title_tks`: 10× weight
   - `important_kwd`: 30× weight (auto-generated keywords)
   - `question_kwd`: 20× weight (auto-generated questions)
   - `content_ltks`: 2× weight (main chunk content)
   - `title_ltks`: 1× weight
   - `content_sm_ltks`: 1× weight (small-grained tokens)

5. **Minimum Match**: 60% of terms must match (drops to 10% on retry)

### Fusion Strategy

**File**: `rag/nlp/search.py` — `Dealer.search()`

```python
# Default: 5% keyword, 95% vector
FusionExpr(
    text_match,
    dense_match,
    method="weighted_sum",
    weights=[1 - vector_similarity_weight, vector_similarity_weight]
)
```

The `vector_similarity_weight` parameter (stored per Dialog) controls the blend. This is the single most important tuning knob.

**Practical Guidance**:
| Use Case | Recommended Weight | Why |
|----------|-------------------|-----|
| General knowledge Q&A | 0.9-0.95 vector | Semantic understanding dominates |
| Technical documentation | 0.7-0.8 vector | Terms matter (error codes, API names) |
| Legal/regulatory | 0.5-0.6 vector | Exact clauses and section numbers critical |
| Product catalog search | 0.3-0.5 vector | SKUs, model numbers need exact match |

### Fallback Logic

If the initial search returns zero results:
1. Retry with minimum match reduced to 10%
2. If still empty, return empty (don't hallucinate)

---

## 3.3 Reranking Logic

### Tier 1: Hybrid Score Reranking

**File**: `rag/nlp/search.py` — `Dealer.rerank()`

After retrieving candidates, RAGFlow computes a combined score:

```python
# For each chunk:
score = (
    tkweight × token_similarity(query_tokens, chunk_tokens) +
    vtweight × vector_cosine_similarity +
    pagerank_boost +
    tag_feature_score
)
```

Where:
- `tkweight` and `vtweight` are derived from `vector_similarity_weight`
- `token_similarity` uses n-gram overlap metrics
- `pagerank_boost` comes from document-level importance (if GraphRAG is enabled)
- `tag_feature_score` adds boost for chunks matching user-specified tags

### Tier 2: Model-Based Reranking (Optional)

**File**: `rag/nlp/search.py` — `Dealer.rerank_by_model()`

When a reranking model is configured:

```python
# Supported rerankers:
# - Jina Reranker v2
# - BGE Reranker v2
# - Cohere Rerank v3.5
# - NVIDIA NeMo Reranker
# - Local cross-encoder models

scores = rerank_model.similarity(query, [chunk.text for chunk in candidates])
# Returns: [(chunk, normalized_score_0_to_1), ...]
```

The reranker completely replaces the hybrid scores — it's a cross-encoder that jointly encodes query and document for more accurate relevance judgment.

### Tier 3: Threshold Filtering

After reranking, chunks below `similarity_threshold` (default 0.2) are dropped.

---

## 3.4 Context Window Construction

**File**: `rag/prompts/generator.py` — `kb_prompt()`

This is the bridge between retrieval and generation:

```python
def kb_prompt(kbinfos, max_tokens, hash_id=False):
    """Format retrieved chunks into LLM context."""
    knowledges = []
    used_token_count = 0
    
    for i, chunk in enumerate(kbinfos["chunks"]):
        # Build structured chunk representation
        cnt = f"\nID: {chunk_id}"
        cnt += f"\n├── Title: {doc_name}"
        if url: cnt += f"\n├── URL: {url}"
        for k, v in metadata.items():
            cnt += f"\n├── {k}: {v}"
        cnt += f"\n└── Content:\n{chunk_content}"
        
        # Token-aware accumulation
        used_token_count += num_tokens_from_string(cnt)
        if max_tokens * 0.97 < used_token_count:
            break  # Stop before overflow
        
        knowledges.append(cnt)
    
    return "\n------\n".join(knowledges)
```

**Key Design Decisions**:
1. **97% threshold**: Leaves 3% headroom for system prompt + generation
2. **Chunk ordering**: Preserves retrieval rank order (highest score first)
3. **Metadata injection**: Includes document title, URL, custom metadata fields
4. **Separator**: `------` between chunks for clear delineation
5. **ID assignment**: Integer IDs for citation format `[ID:X]`

---

## 3.5 Advanced Retrieval Features

### Multi-turn Query Refinement

**File**: `api/db/services/dialog_service.py`

For multi-turn conversations, RAGFlow combines the last 3 messages into a single refined query:

```python
# LLM prompt: "Given the conversation history, produce a single standalone question"
# Input: last 3 user messages
# Output: refined query that captures full intent
```

This prevents the common problem of "What about the second one?" (where "second one" refers to context from 3 turns ago).

### Knowledge Graph Augmentation

**File**: `rag/graphrag/search.py`

When GraphRAG is enabled for a KB:
1. Extract entity types and keywords from query
2. Retrieve matching entities by keyword (dense) and type (PageRank sorted)
3. N-hop expansion: neighbors with distance-dampened scoring (`sim / (2 + hop_distance)`)
4. Community reports: retrieve cluster summaries for high-level context

This adds relational context that chunk-based retrieval misses.

### TOC-Based Section Expansion

When a PDF has a Table of Contents, RAGFlow can:
1. Retrieve the TOC structure
2. Find sections related to the query
3. Expand retrieval to include adjacent sections

---

## 3.6 How to Improve Retrieval Quality in Our System

### Architecture Recommendations

```
┌─────────────────────────────────────────────────┐
│                  Query Pipeline                  │
├─────────────────────────────────────────────────┤
│ 1. Query Understanding                          │
│    ├── Intent classification                    │
│    ├── Entity extraction                        │
│    ├── Multi-turn refinement (LLM)              │
│    └── Query expansion (synonyms + rephrase)    │
│                                                 │
│ 2. Retrieval                                    │
│    ├── Dense vector search (Qdrant)             │
│    ├── Sparse vector search (BM25 via Qdrant)   │
│    ├── Metadata filtering                       │
│    └── Hybrid fusion (configurable weights)     │
│                                                 │
│ 3. Reranking                                    │
│    ├── Cross-encoder reranker (Cohere/Jina)     │
│    ├── Threshold filtering                      │
│    └── Deduplication (near-duplicate removal)   │
│                                                 │
│ 4. Context Construction                         │
│    ├── Token-aware chunk assembly               │
│    ├── Metadata injection                       │
│    ├── Parent chunk expansion (optional)        │
│    └── Citation ID assignment                   │
└─────────────────────────────────────────────────┘
```

### Specific Improvements Over RAGFlow

1. **Late Interaction Models**: Use ColBERT-style late interaction instead of single-vector cosine. Qdrant supports multi-vector search.

2. **Reciprocal Rank Fusion (RRF)**: Instead of weighted sum, use RRF for combining BM25 and vector results. More robust to score distribution differences.
   ```python
   def rrf_score(ranks, k=60):
       return sum(1.0 / (k + rank) for rank in ranks)
   ```

3. **Query Decomposition**: For complex queries, decompose into sub-queries, retrieve separately, then merge results. RAGFlow doesn't do this.

4. **Sparse + Dense in Qdrant**: Use Qdrant's native sparse vector support for BM25-style matching. No need for a separate Elasticsearch instance.

5. **Adaptive Retrieval**: Based on query complexity, adjust the number of retrieved chunks dynamically. Simple factual → 3-5 chunks; complex analytical → 10-20 chunks.

6. **Answer Verification**: After generation, verify each cited chunk actually supports the claim. RAGFlow does basic auto-citation but no verification.

7. **Caching**: Cache embedding vectors for repeated queries. RAGFlow doesn't cache.

### Qdrant-Specific Implementation

```python
from qdrant_client import QdrantClient, models

# Create collection with hybrid search
client.create_collection(
    collection_name="knowledge_base_{kb_id}",
    vectors_config={
        "dense": models.VectorParams(size=768, distance=models.Distance.COSINE),
    },
    sparse_vectors_config={
        "bm25": models.SparseVectorParams(
            modifier=models.Modifier.IDF,
        ),
    },
)

# Hybrid search
results = client.query_points(
    collection_name="knowledge_base_{kb_id}",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm25", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=20,
)
```
