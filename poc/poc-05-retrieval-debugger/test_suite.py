"""Batch test suite runner with Recall@K metrics."""
import logging

from debugger import RetrievalDebugger

logger = logging.getLogger(__name__)


class TestSuiteRunner:
    """Run batch retrieval tests and compute IR metrics.

    Supports:
    - Recall@K: fraction of expected chunks found in top K
    - Keyword hit rate: fraction of expected keywords found in retrieved content
    - Per-query breakdowns
    """

    def __init__(self, debugger: RetrievalDebugger):
        self.debugger = debugger

    async def run(
        self,
        kb_ids: list[str],
        test_cases: list[dict],
        top_k: int = 20,
        final_k: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
    ) -> dict:
        """Run all test cases and compute metrics.

        Args:
            kb_ids: Knowledge bases to search
            test_cases: List of dicts with 'query', 'expected_chunk_ids', 'expected_keywords'
            top_k: Initial recall
            final_k: Final result count

        Returns:
            Aggregate metrics + per-query results
        """
        results = []
        total_recall = 0.0
        total_keyword_hit = 0.0

        for tc in test_cases:
            query = tc["query"]
            expected_ids = set(tc.get("expected_chunk_ids", []))
            expected_keywords = [kw.lower() for kw in tc.get("expected_keywords", [])]

            search_result = await self.debugger.debug_search(
                query=query,
                kb_ids=kb_ids,
                top_k=top_k,
                final_k=final_k,
                dense_weight=dense_weight,
                sparse_weight=sparse_weight,
            )

            retrieved_ids = {r["chunk_id"] for r in search_result["results"]}
            retrieved_text = " ".join(r.get("content_preview", "") for r in search_result["results"]).lower()

            # Recall@K
            recall = 0.0
            if expected_ids:
                found = expected_ids & retrieved_ids
                recall = len(found) / len(expected_ids)

            # Keyword hit rate
            keyword_hit = 0.0
            if expected_keywords:
                hits = sum(1 for kw in expected_keywords if kw in retrieved_text)
                keyword_hit = hits / len(expected_keywords)

            total_recall += recall
            total_keyword_hit += keyword_hit

            results.append({
                "query": query,
                "recall_at_k": round(recall, 4),
                "keyword_hit_rate": round(keyword_hit, 4),
                "expected_ids": sorted(expected_ids),
                "found_ids": sorted(expected_ids & retrieved_ids),
                "missing_ids": sorted(expected_ids - retrieved_ids),
                "expected_keywords": expected_keywords,
                "retrieved_count": len(search_result["results"]),
                "timings_ms": search_result["timings_ms"],
            })

        n = len(test_cases)
        return {
            "summary": {
                "total_tests": n,
                "avg_recall_at_k": round(total_recall / n, 4) if n else 0,
                "avg_keyword_hit_rate": round(total_keyword_hit / n, 4) if n else 0,
                "config": {
                    "top_k": top_k,
                    "final_k": final_k,
                    "dense_weight": dense_weight,
                    "sparse_weight": sparse_weight,
                },
            },
            "test_results": results,
        }
