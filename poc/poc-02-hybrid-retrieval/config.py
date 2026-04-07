"""Retrieval configuration models."""
from dataclasses import dataclass, field
from enum import Enum


class FusionMethod(str, Enum):
    RRF = "rrf"  # Reciprocal Rank Fusion
    WEIGHTED_SUM = "weighted_sum"  # Linear combination of scores


@dataclass
class RetrievalConfig:
    """Full retrieval pipeline configuration.

    Mirrors RAGFlow's Dealer.search() parameters from rag/nlp/search.py
    """
    # Search params
    top_k: int = 20  # Initial recall count
    final_k: int = 5  # Results after reranking/filtering
    similarity_threshold: float = 0.2  # Minimum score to keep

    # Fusion weights (must sum to 1.0)
    dense_weight: float = 0.7  # Semantic similarity weight
    sparse_weight: float = 0.3  # BM25 keyword weight
    fusion_method: FusionMethod = FusionMethod.RRF

    # RRF parameter
    rrf_k: int = 60  # RRF constant (higher = more equal weighting)

    # Reranking
    rerank_model: str | None = None  # e.g. "rerank-english-v3.0" or None to skip
    rerank_top_k: int | None = None  # How many to rerank (defaults to top_k)

    # Context assembly
    max_context_tokens: int = 4096  # Max tokens for LLM context window
    chunk_separator: str = "\n---\n"

    # Query
    boost_title_weight: float = 1.5  # Extra weight for title field matches
    boost_keywords_weight: float = 1.2  # Extra weight for keyword matches

    def validate(self) -> None:
        if not (0 <= self.dense_weight <= 1 and 0 <= self.sparse_weight <= 1):
            raise ValueError("Weights must be between 0 and 1")
        if abs(self.dense_weight + self.sparse_weight - 1.0) > 0.01:
            raise ValueError("dense_weight + sparse_weight must equal 1.0")
        if self.similarity_threshold < 0 or self.similarity_threshold > 1:
            raise ValueError("similarity_threshold must be between 0 and 1")


@dataclass
class SearchResult:
    """A single search result with score breakdown."""
    chunk_id: str
    content: str
    document_id: str
    document_name: str
    kb_id: str
    chunk_order: int = 0

    # Score breakdown
    dense_score: float = 0.0
    sparse_score: float = 0.0
    combined_score: float = 0.0
    rerank_score: float | None = None
    final_score: float = 0.0

    # Metadata
    metadata: dict = field(default_factory=dict)

    def score_breakdown(self) -> dict:
        return {
            "dense": round(self.dense_score, 4),
            "sparse": round(self.sparse_score, 4),
            "combined": round(self.combined_score, 4),
            "rerank": round(self.rerank_score, 4) if self.rerank_score is not None else None,
            "final": round(self.final_score, 4),
        }
