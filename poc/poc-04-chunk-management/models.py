"""Pydantic models for chunk management API."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChunkStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ALL = "all"


class ChunkCreate(BaseModel):
    """Request to manually create a chunk."""
    kb_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, max_length=50000)
    document_id: str = Field(default="manual")
    document_name: str = Field(default="Manual Entry")
    metadata: dict = Field(default_factory=dict)


class ChunkUpdate(BaseModel):
    """Request to update chunk content (triggers re-embedding)."""
    content: str = Field(..., min_length=1, max_length=50000)
    metadata: dict | None = None


class ChunkToggle(BaseModel):
    """Request to toggle chunk active status."""
    is_active: bool


class BatchAction(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"


class BatchRequest(BaseModel):
    """Batch operation on multiple chunks."""
    chunk_ids: list[str] = Field(..., min_length=1, max_length=500)
    kb_id: str
    action: BatchAction


class ChunkResponse(BaseModel):
    """Single chunk response."""
    chunk_id: str
    content: str
    document_id: str
    document_name: str
    kb_id: str
    chunk_order: int = 0
    is_active: bool = True
    token_count: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ChunkListResponse(BaseModel):
    """Paginated chunk list response."""
    total: int
    page: int
    page_size: int
    chunks: list[ChunkResponse]


class BatchResponse(BaseModel):
    """Batch operation response."""
    action: str
    total: int
    succeeded: int
    failed: int
    errors: list[str] = Field(default_factory=list)
