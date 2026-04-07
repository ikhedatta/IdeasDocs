"""Pydantic models for knowledge base management."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ParserConfig(BaseModel):
    """Parser configuration for a knowledge base."""
    chunk_token_size: int = Field(default=512, ge=64, le=4096)
    chunk_overlap_percent: float = Field(default=0.1, ge=0.0, le=0.5)
    delimiter: str = Field(default="\n!?。；！？")
    pdf_parser: str = Field(default="auto", description="auto, pymupdf, ocr, structured")
    extract_tables: bool = True
    extract_images: bool = False
    language: str = Field(default="english")


class DocumentStatus(str, Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


# --- KB Models ---


class KBCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    parser_config: ParserConfig = Field(default_factory=ParserConfig)
    tags: list[str] = Field(default_factory=list)


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    parser_config: ParserConfig | None = None
    tags: list[str] | None = None


class KBResponse(BaseModel):
    id: str
    name: str
    description: str
    parser_config: ParserConfig
    tags: list[str]
    created_at: str
    updated_at: str
    document_count: int = 0
    chunk_count: int = 0


class KBStats(BaseModel):
    kb_id: str
    kb_name: str
    document_count: int
    documents_by_status: dict[str, int]
    chunk_count: int
    active_chunks: int
    inactive_chunks: int
    estimated_tokens: int


# --- Document Models ---


class DocumentResponse(BaseModel):
    id: str
    kb_id: str
    name: str
    file_type: str
    file_size: int = 0
    status: DocumentStatus
    chunk_count: int = 0
    error_message: str | None = None
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentResponse]
