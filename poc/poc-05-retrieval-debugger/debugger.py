"""Core debug retrieval with full tracing and score decomposition."""
import logging
import time

import litellm
from qdrant_client import QdrantClient, models

logger = logging.getLogger(__name__)


class RetrievalDebugger:
    """Debug-oriented retrieval that exposes all intermediate scores and timings."""

    def __init__(self, qdrant_url: str = "http://localhost:6333", embedding_model: str = "text-embedding-3-small"):
        self.client = QdrantClient(url=qdrant_url)
        self.embedding_model = embedding_model

    async def debug_search(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 20,
        final_k: int = 10,
        similarity_threshold: float = 0.0,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        rerank_model: str | None = None,
    ) -> dict:
        """Search with full debug output: per-chunk scores, timings, and counts at each stage."""
        timings = {}

        # 1. Embed query
        t0 = time.perf_counter()
        resp = await litellm.aembedding(model=self.embedding_model, input=[query])
        query_vector = resp.data[0]["embedding"]
        timings["embed_ms"] = round((time.perf_counter() - t0) * 1000)

        # 2. Search each KB
        t1 = time.perf_counter()
        all_results = []
        for kb_id in kb_ids:
            collection = f"kb_{kb_id}"
            try:
                results = self._search_with_scores(collection, query_vector, top_k)
                for r in results:
                    r["kb_id"] = kb_id
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for {collection}: {e}")
        timings["search_ms"] = round((time.perf_counter() - t1) * 1000)

        total_candidates = len(all_results)

        # 3. Sort by dense score (primary retrieval)
        all_results.sort(key=lambda r: r["dense_score"], reverse=True)

        # 4. Apply threshold
        after_threshold = [r for r in all_results if r["dense_score"] >= similarity_threshold]
        after_threshold_count = len(after_threshold)

        # 5. Rerank (optional)
        t2 = time.perf_counter()
        if rerank_model and after_threshold:
            after_threshold = await self._rerank(query, after_threshold, rerank_model, final_k)
        timings["rerank_ms"] = round((time.perf_counter() - t2) * 1000)

        # 6. Assign final scores
        for r in after_threshold:
            if r.get("rerank_score") is not None:
                r["final_score"] = r["rerank_score"]
            else:
                r["final_score"] = dense_weight * r["dense_score"] + sparse_weight * r.get("sparse_score", 0.0)
                r["combined_score"] = r["final_score"]

        after_threshold.sort(key=lambda r: r["final_score"], reverse=True)
        final_results = after_threshold[:final_k]

        timings["total_ms"] = round((time.perf_counter() - t0) * 1000)

        # Build debug output
        debug_results = []
        for rank, r in enumerate(final_results, 1):
            content = r.get("content", "")
            debug_results.append({
                "rank": rank,
                "chunk_id": r["chunk_id"],
                "content_preview": content[:150] + "..." if len(content) > 150 else content,
                "document_name": r.get("document_name", ""),
                "dense_score": round(r.get("dense_score", 0.0), 4),
                "sparse_score": round(r.get("sparse_score", 0.0), 4),
                "combined_score": round(r.get("combined_score", 0.0), 4),
                "rerank_score": round(r["rerank_score"], 4) if r.get("rerank_score") is not None else None,
                "final_score": round(r.get("final_score", 0.0), 4),
            })

        return {
            "query": query,
            "config": {
                "top_k": top_k,
                "final_k": final_k,
                "similarity_threshold": similarity_threshold,
                "dense_weight": dense_weight,
                "sparse_weight": sparse_weight,
                "rerank_model": rerank_model,
            },
            "timings_ms": timings,
            "total_candidates": total_candidates,
            "after_threshold": after_threshold_count,
            "final_count": len(final_results),
            "results": debug_results,
        }

    def _search_with_scores(
        self, collection: str, query_vector: list[float], top_k: int
    ) -> list[dict]:
        """Search Qdrant and return results with score breakdown."""
        results = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            using="dense",
            limit=top_k,
            with_payload=True,
        )

        out = []
        for point in results.points:
            payload = point.payload or {}
            out.append({
                "chunk_id": str(point.id),
                "content": payload.get("content", ""),
                "document_name": payload.get("document_name", ""),
                "document_id": payload.get("document_id", ""),
                "dense_score": point.score or 0.0,
                "sparse_score": 0.0,
                "combined_score": point.score or 0.0,
                "rerank_score": None,
            })
        return out

    async def _rerank(
        self, query: str, results: list[dict], model: str, top_k: int
    ) -> list[dict]:
        """Rerank using cross-encoder."""
        import httpx

        documents = [r["content"] for r in results]
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                api_key = __import__("os").getenv("COHERE_API_KEY", "")
                resp = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={"model": model, "query": query, "documents": documents, "top_n": top_k},
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

            reranked = []
            for item in data["results"]:
                idx = item["index"]
                r = results[idx]
                r["rerank_score"] = item["relevance_score"]
                reranked.append(r)
            return reranked
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            return results[:top_k]

    async def compare(
        self,
        query: str,
        kb_ids: list[str],
        config_a: dict,
        config_b: dict,
    ) -> dict:
        """Run same query with two configs and compare results."""
        result_a = await self.debug_search(query, kb_ids, **config_a)
        result_b = await self.debug_search(query, kb_ids, **config_b)

        ids_a = [r["chunk_id"] for r in result_a["results"]]
        ids_b = [r["chunk_id"] for r in result_b["results"]]
        set_a = set(ids_a)
        set_b = set(ids_b)

        # Rank correlation: Kendall's tau approximation via position changes
        rank_changes = []
        for cid in set_a & set_b:
            pos_a = ids_a.index(cid)
            pos_b = ids_b.index(cid)
            rank_changes.append({"chunk_id": cid, "rank_a": pos_a + 1, "rank_b": pos_b + 1, "change": pos_a - pos_b})

        return {
            "query": query,
            "config_a": result_a,
            "config_b": result_b,
            "comparison": {
                "shared_chunks": len(set_a & set_b),
                "only_in_a": len(set_a - set_b),
                "only_in_b": len(set_b - set_a),
                "jaccard_similarity": len(set_a & set_b) / len(set_a | set_b) if set_a | set_b else 0.0,
                "rank_changes": sorted(rank_changes, key=lambda x: abs(x["change"]), reverse=True),
            },
        }
