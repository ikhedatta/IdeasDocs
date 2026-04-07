"""Request/response models for retrieval debugger."""
from pydantic import BaseModel, Field


class DebugSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    kb_ids: list[str] = Field(..., min_length=1)
    top_k: int = Field(default=20, ge=1, le=100)
    final_k: int = Field(default=10, ge=1, le=50)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    dense_weight: float = Field(default=0.7, ge=0.0, le=1.0)
    sparse_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    rerank_model: str | None = None


class CompareConfig(BaseModel):
    top_k: int = Field(default=20)
    final_k: int = Field(default=10)
    similarity_threshold: float = Field(default=0.0)
    dense_weight: float = Field(default=0.7)
    sparse_weight: float = Field(default=0.3)
    rerank_model: str | None = None


class CompareRequest(BaseModel):
    query: str = Field(..., min_length=1)
    kb_ids: list[str] = Field(..., min_length=1)
    config_a: CompareConfig = Field(default_factory=CompareConfig)
    config_b: CompareConfig = Field(default_factory=CompareConfig)


class TestCase(BaseModel):
    """Single test case: query + expected chunk IDs or keywords."""
    query: str
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_keywords: list[str] = Field(default_factory=list)


class BatchTestRequest(BaseModel):
    kb_ids: list[str] = Field(..., min_length=1)
    test_cases: list[TestCase] = Field(..., min_length=1)
    top_k: int = Field(default=20)
    final_k: int = Field(default=10)
    dense_weight: float = Field(default=0.7)
    sparse_weight: float = Field(default=0.3)


class DebugChunkResult(BaseModel):
    rank: int
    chunk_id: str
    content_preview: str
    document_name: str
    dense_score: float
    sparse_score: float
    combined_score: float
    rerank_score: float | None = None
    final_score: float


class DebugSearchResponse(BaseModel):
    query: str
    config: dict
    timings_ms: dict
    total_candidates: int
    after_threshold: int
    final_count: int
    results: list[DebugChunkResult]
