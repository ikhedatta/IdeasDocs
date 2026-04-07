"""Cross-encoder reranking via litellm or direct API calls.

Implements the reranking step from RAGFlow's rag/llm/rerank_model.py:
- Takes initial recall results
- Re-scores with a cross-encoder model
- Returns reordered results with updated scores
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker supporting multiple providers.

    Supported providers:
    - Cohere (rerank-english-v3.0, rerank-multilingual-v3.0)
    - Jina (jina-reranker-v2-base-multilingual)
    - BAAI/bge-reranker via local API
    """

    # Provider detection from model name
    PROVIDER_MAP = {
        "rerank-english": "cohere",
        "rerank-multilingual": "cohere",
        "jina-reranker": "jina",
        "bge-reranker": "local",
    }

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("RERANK_API_KEY") or os.getenv("COHERE_API_KEY", "")
        self.base_url = base_url
        self.provider = self._detect_provider()

    def _detect_provider(self) -> str:
        for prefix, provider in self.PROVIDER_MAP.items():
            if prefix in self.model.lower():
                return provider
        return "cohere"  # Default to Cohere

    async def rerank(
        self, query: str, documents: list[str], top_k: int | None = None
    ) -> list[tuple[int, float]]:
        """Rerank documents for the given query.

        Returns list of (original_index, score) sorted by score descending.
        """
        if not documents:
            return []

        try:
            if self.provider == "cohere":
                return await self._rerank_cohere(query, documents, top_k)
            elif self.provider == "jina":
                return await self._rerank_jina(query, documents, top_k)
            else:
                return await self._rerank_local(query, documents, top_k)
        except Exception as e:
            logger.warning(f"Reranking failed ({self.model}): {e}. Returning original order.")
            # Graceful fallback: return original order with decaying scores
            return [(i, 1.0 - i * 0.01) for i in range(len(documents))]

    async def _rerank_cohere(
        self, query: str, documents: list[str], top_k: int | None
    ) -> list[tuple[int, float]]:
        """Rerank using Cohere's rerank API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
            }
            if top_k:
                payload["top_n"] = top_k

            resp = await client.post(
                "https://api.cohere.ai/v1/rerank",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = [(r["index"], r["relevance_score"]) for r in data["results"]]
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def _rerank_jina(
        self, query: str, documents: list[str], top_k: int | None
    ) -> list[tuple[int, float]]:
        """Rerank using Jina's rerank API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
            }
            if top_k:
                payload["top_n"] = top_k

            resp = await client.post(
                "https://api.jina.ai/v1/rerank",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = [(r["index"], r["relevance_score"]) for r in data["results"]]
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    async def _rerank_local(
        self, query: str, documents: list[str], top_k: int | None
    ) -> list[tuple[int, float]]:
        """Rerank using a locally hosted model (e.g., TEI or vLLM reranking endpoint)."""
        base = self.base_url or "http://localhost:8787"
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": self.model,
                "query": query,
                "documents": documents,
            }
            if top_k:
                payload["top_n"] = top_k

            resp = await client.post(
                f"{base}/v1/rerank",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = [(r["index"], r["relevance_score"]) for r in data["results"]]
        results.sort(key=lambda x: x[1], reverse=True)
        return results
