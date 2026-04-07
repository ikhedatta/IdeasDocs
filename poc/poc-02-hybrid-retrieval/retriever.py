"""Core hybrid retrieval engine using Qdrant.

Implements the full retrieval pipeline:
1. Encode query → dense + sparse vectors
2. Qdrant hybrid search with configurable fusion
3. Optional cross-encoder reranking
4. Threshold filtering
5. Token-aware context assembly
"""
import logging
import time
from dataclasses import dataclass

import litellm
from qdrant_client import QdrantClient, models

from config import FusionMethod, RetrievalConfig, SearchResult
from context_builder import ContextBuilder
from reranker import Reranker
from sparse_encoder import SparseEncoder

logger = logging.getLogger(__name__)


@dataclass
class RetrievalTrace:
    """Timing and debug info for a retrieval call."""
    query: str
    config: dict
    timings_ms: dict
    initial_count: int
    after_threshold_count: int
    after_rerank_count: int
    final_count: int
    results: list[dict]


class HybridRetriever:
    """Hybrid retrieval engine combining dense and sparse search.

    Mirrors RAGFlow's Dealer class from rag/nlp/search.py with:
    - Configurable fusion (RRF or weighted sum)
    - Multi-collection search (multiple knowledge bases)
    - Cross-encoder reranking
    - Score decomposition for debugging
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.client = QdrantClient(url=qdrant_url)
        self.embedding_model = embedding_model
        self.sparse_encoder = SparseEncoder()

    async def _embed_query(self, query: str) -> list[float]:
        """Embed query using litellm."""
        resp = await litellm.aembedding(model=self.embedding_model, input=[query])
        return resp.data[0]["embedding"]

    async def search(
        self,
        query: str,
        kb_ids: list[str],
        config: RetrievalConfig | None = None,
    ) -> list[SearchResult]:
        """Execute hybrid search across one or more knowledge bases.

        Args:
            query: User query string
            kb_ids: Knowledge base IDs (each maps to a Qdrant collection "kb_{id}")
            config: Retrieval configuration (uses defaults if None)

        Returns:
            Ranked list of SearchResult with score breakdowns
        """
        config = config or RetrievalConfig()
        config.validate()

        t0 = time.perf_counter()

        # 1. Encode query
        dense_vector = await self._embed_query(query)
        sparse_vector = self.sparse_encoder.encode_query(query)
        t_encode = time.perf_counter()

        # 2. Search across all knowledge bases
        all_results: list[SearchResult] = []
        for kb_id in kb_ids:
            collection = f"kb_{kb_id}"
            try:
                results = self._search_collection(
                    collection, dense_vector, sparse_vector, config, kb_id
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for collection {collection}: {e}")
        t_search = time.perf_counter()

        # 3. Merge and sort by combined score
        all_results.sort(key=lambda r: r.combined_score, reverse=True)

        # 4. Threshold filtering
        all_results = [
            r for r in all_results if r.combined_score >= config.similarity_threshold
        ]

        # 5. Optional reranking
        if config.rerank_model and all_results:
            rerank_count = config.rerank_top_k or config.top_k
            to_rerank = all_results[:rerank_count]
            reranker = Reranker(model=config.rerank_model)
            reranked = await reranker.rerank(
                query=query,
                documents=[r.content for r in to_rerank],
                top_k=config.final_k,
            )
            # Apply rerank scores
            reranked_results = []
            for orig_idx, score in reranked:
                result = to_rerank[orig_idx]
                result.rerank_score = score
                result.final_score = score
                reranked_results.append(result)
            all_results = reranked_results
        else:
            # Without reranking, final_score = combined_score
            for r in all_results:
                r.final_score = r.combined_score
        t_rerank = time.perf_counter()

        # 6. Trim to final_k
        all_results = all_results[: config.final_k]

        logger.info(
            f"Hybrid search: encode={1000*(t_encode-t0):.0f}ms "
            f"search={1000*(t_search-t_encode):.0f}ms "
            f"rerank={1000*(t_rerank-t_search):.0f}ms "
            f"results={len(all_results)}"
        )

        return all_results

    def _search_collection(
        self,
        collection: str,
        dense_vector: list[float],
        sparse_vector,
        config: RetrievalConfig,
        kb_id: str,
    ) -> list[SearchResult]:
        """Search a single Qdrant collection with hybrid query."""

        # Build prefetch queries for dense and sparse
        dense_prefetch = models.Prefetch(
            query=dense_vector,
            using="dense",
            limit=config.top_k,
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="is_active", match=models.MatchValue(value=True)
                    )
                ]
            ),
        )

        sparse_prefetch = models.Prefetch(
            query=models.SparseVector(
                indices=sparse_vector.indices,
                values=sparse_vector.values,
            ),
            using="bm25",
            limit=config.top_k,
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="is_active", match=models.MatchValue(value=True)
                    )
                ]
            ),
        )

        # Execute hybrid query with RRF fusion
        if config.fusion_method == FusionMethod.RRF:
            results = self.client.query_points(
                collection_name=collection,
                prefetch=[dense_prefetch, sparse_prefetch],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=config.top_k,
                with_payload=True,
            )
        else:
            # Weighted sum approach: search separately and combine
            return self._weighted_sum_search(
                collection, dense_vector, sparse_vector, config, kb_id
            )

        # Convert Qdrant results to SearchResult
        search_results = []
        for point in results.points:
            payload = point.payload or {}
            sr = SearchResult(
                chunk_id=str(point.id),
                content=payload.get("content", ""),
                document_id=payload.get("document_id", ""),
                document_name=payload.get("document_name", ""),
                kb_id=kb_id,
                chunk_order=payload.get("chunk_order", 0),
                combined_score=point.score if point.score else 0.0,
                metadata={
                    k: v
                    for k, v in payload.items()
                    if k not in ("content", "document_id", "document_name", "chunk_order")
                },
            )
            search_results.append(sr)

        return search_results

    def _weighted_sum_search(
        self,
        collection: str,
        dense_vector: list[float],
        sparse_vector,
        config: RetrievalConfig,
        kb_id: str,
    ) -> list[SearchResult]:
        """Fallback: search dense and sparse separately, combine with weighted sum."""
        active_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="is_active", match=models.MatchValue(value=True)
                )
            ]
        )

        # Dense search
        dense_results = self.client.query_points(
            collection_name=collection,
            query=dense_vector,
            using="dense",
            limit=config.top_k,
            with_payload=True,
            query_filter=active_filter,
        )

        # Sparse search
        sparse_results = self.client.query_points(
            collection_name=collection,
            query=models.SparseVector(
                indices=sparse_vector.indices,
                values=sparse_vector.values,
            ),
            using="bm25",
            limit=config.top_k,
            with_payload=True,
            query_filter=active_filter,
        )

        # Build score maps
        dense_scores = {}
        point_data = {}
        for p in dense_results.points:
            pid = str(p.id)
            dense_scores[pid] = p.score or 0.0
            point_data[pid] = p.payload or {}

        sparse_scores = {}
        for p in sparse_results.points:
            pid = str(p.id)
            sparse_scores[pid] = p.score or 0.0
            if pid not in point_data:
                point_data[pid] = p.payload or {}

        # Combine scores
        all_ids = set(dense_scores) | set(sparse_scores)
        results = []
        for pid in all_ids:
            d_score = dense_scores.get(pid, 0.0)
            s_score = sparse_scores.get(pid, 0.0)
            combined = config.dense_weight * d_score + config.sparse_weight * s_score
            payload = point_data[pid]

            results.append(
                SearchResult(
                    chunk_id=pid,
                    content=payload.get("content", ""),
                    document_id=payload.get("document_id", ""),
                    document_name=payload.get("document_name", ""),
                    kb_id=kb_id,
                    chunk_order=payload.get("chunk_order", 0),
                    dense_score=d_score,
                    sparse_score=s_score,
                    combined_score=combined,
                    metadata={
                        k: v
                        for k, v in payload.items()
                        if k not in ("content", "document_id", "document_name", "chunk_order")
                    },
                )
            )

        results.sort(key=lambda r: r.combined_score, reverse=True)
        return results

    async def search_with_context(
        self,
        query: str,
        kb_ids: list[str],
        config: RetrievalConfig | None = None,
    ) -> dict:
        """Search and build LLM-ready context.

        Returns dict with results, context, sources, and token usage.
        """
        config = config or RetrievalConfig()
        results = await self.search(query, kb_ids, config)

        builder = ContextBuilder(max_tokens=config.max_context_tokens)
        prompt_context = builder.build_prompt_context(results, query)

        return {
            "query": query,
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "content": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                    "document_name": r.document_name,
                    "scores": r.score_breakdown(),
                }
                for r in results
            ],
            "context": prompt_context["context"],
            "sources": prompt_context["sources"],
            "token_usage": prompt_context["token_usage"],
        }
