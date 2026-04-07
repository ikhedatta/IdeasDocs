"""Full RAG pipeline: retrieve → format → generate → extract citations.

This orchestrates the complete flow from question to cited answer.
"""
import logging
import time
from dataclasses import dataclass

import litellm
from qdrant_client import QdrantClient, models

from citation_extractor import CitationExtractor, CitationResult
from llm_client import LLMClient
from prompt_templates import build_system_prompt, format_context_chunks

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig:
    """Configuration for the RAG pipeline."""
    # Retrieval
    top_k: int = 10
    final_k: int = 5
    similarity_threshold: float = 0.2

    # LLM
    llm_model: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 2048

    # Prompt
    prompt_template: str = "default"  # "default", "strict", "conversational"

    # Context
    max_context_tokens: int = 4096

    # Embedding
    embedding_model: str = "text-embedding-3-small"


@dataclass
class RAGResponse:
    """Full RAG response with answer, citations, and debug info."""
    question: str
    answer: str
    citations: list[dict]
    confidence: str
    citation_coverage: float
    source_chunks: list[dict]
    timings_ms: dict
    token_usage: dict

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": self.citations,
            "confidence": self.confidence,
            "citation_coverage": self.citation_coverage,
            "source_count": len(self.source_chunks),
            "timings_ms": self.timings_ms,
            "token_usage": self.token_usage,
        }


class RAGPipeline:
    """Citation-enforced RAG pipeline.

    Implements the full flow:
    1. Embed query → search Qdrant
    2. Format chunks as numbered context
    3. Build citation-enforcing system prompt
    4. Generate answer with LLM
    5. Extract and validate citations
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        config: RAGConfig | None = None,
    ):
        self.config = config or RAGConfig()
        self.client = QdrantClient(url=qdrant_url)
        self.llm = LLMClient(
            model=self.config.llm_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        self.citation_extractor = CitationExtractor()

    async def ask(
        self,
        question: str,
        kb_ids: list[str],
        config: RAGConfig | None = None,
    ) -> RAGResponse:
        """Ask a question and get a cited answer.

        Args:
            question: User's question
            kb_ids: Knowledge base IDs to search
            config: Override default config for this request

        Returns:
            RAGResponse with answer, citations, and debug info
        """
        cfg = config or self.config
        timings = {}

        # Step 1: Embed query
        t0 = time.perf_counter()
        query_vector = await self._embed_query(question, cfg.embedding_model)
        timings["embed_ms"] = round((time.perf_counter() - t0) * 1000)

        # Step 2: Retrieve chunks from all KBs
        t1 = time.perf_counter()
        chunks = []
        for kb_id in kb_ids:
            collection = f"kb_{kb_id}"
            try:
                kb_chunks = self._search_chunks(collection, query_vector, cfg)
                chunks.extend(kb_chunks)
            except Exception as e:
                logger.warning(f"Search failed for {collection}: {e}")
        timings["retrieve_ms"] = round((time.perf_counter() - t1) * 1000)

        # Sort by score and take top_k
        chunks.sort(key=lambda c: c["score"], reverse=True)
        chunks = chunks[: cfg.final_k]

        # Step 3: Handle empty results
        if not chunks:
            return RAGResponse(
                question=question,
                answer="I cannot answer this question based on the available documents.",
                citations=[],
                confidence="no_context",
                citation_coverage=0.0,
                source_chunks=[],
                timings_ms=timings,
                token_usage={},
            )

        # Step 4: Format context and build prompt
        t2 = time.perf_counter()
        context_text = format_context_chunks(chunks)
        system_prompt = build_system_prompt(context_text, cfg.prompt_template)
        timings["format_ms"] = round((time.perf_counter() - t2) * 1000)

        # Step 5: Generate answer
        t3 = time.perf_counter()
        answer = await self.llm.generate(system_prompt, question)
        timings["generate_ms"] = round((time.perf_counter() - t3) * 1000)

        # Step 6: Extract and validate citations
        t4 = time.perf_counter()
        citation_result: CitationResult = self.citation_extractor.extract(answer, chunks)
        timings["citation_ms"] = round((time.perf_counter() - t4) * 1000)

        timings["total_ms"] = round((time.perf_counter() - t0) * 1000)

        return RAGResponse(
            question=question,
            answer=citation_result.answer,
            citations=citation_result.to_dict()["citations"],
            confidence=citation_result.confidence,
            citation_coverage=citation_result.citation_coverage,
            source_chunks=[
                {
                    "index": i + 1,
                    "content": c["content"][:200],
                    "document_name": c.get("document_name", ""),
                    "score": round(c["score"], 4),
                }
                for i, c in enumerate(chunks)
            ],
            timings_ms=timings,
            token_usage={
                "model": cfg.llm_model,
                "prompt_template": cfg.prompt_template,
            },
        )

    async def _embed_query(self, query: str, model: str) -> list[float]:
        """Embed query text."""
        resp = await litellm.aembedding(model=model, input=[query])
        return resp.data[0]["embedding"]

    def _search_chunks(
        self, collection: str, query_vector: list[float], cfg: RAGConfig
    ) -> list[dict]:
        """Search a Qdrant collection for relevant chunks."""
        results = self.client.query_points(
            collection_name=collection,
            query=query_vector,
            using="dense",
            limit=cfg.top_k,
            with_payload=True,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="is_active", match=models.MatchValue(value=True)
                    )
                ]
            ),
            score_threshold=cfg.similarity_threshold,
        )

        chunks = []
        for point in results.points:
            payload = point.payload or {}
            chunks.append(
                {
                    "content": payload.get("content", ""),
                    "document_name": payload.get("document_name", ""),
                    "document_id": payload.get("document_id", ""),
                    "chunk_id": str(point.id),
                    "score": point.score or 0.0,
                    "chunk_order": payload.get("chunk_order", 0),
                }
            )

        return chunks
