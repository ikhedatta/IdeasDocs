"""
Data models for the document processing pipeline.
These models flow through: Parser → Chunker → Embedder → Store
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4


class BlockType(str, Enum):
    """Content block types detected during parsing."""
    TEXT = "text"
    HEADER = "header"
    TABLE = "table"
    FIGURE = "figure"
    LIST = "list"
    CODE = "code"
    FOOTER = "footer"
    CAPTION = "caption"


@dataclass
class ContentBlock:
    """
    Output from a parser — a typed region of a document.
    
    RAGFlow Insight: Documents are NOT flat text. They have structure
    (headers, tables, images, paragraphs). Preserving block types
    during parsing enables smarter chunking (e.g., tables as atomic units).
    
    Source: deepdoc/parser/ — all parsers produce structured boxes
    """
    text: str
    block_type: BlockType = BlockType.TEXT
    page_number: Optional[int] = None
    position: Optional[dict] = None  # {x, y, w, h} for PDF coordinates
    language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    """
    A semantic chunk ready for embedding and storage.
    
    RAGFlow Insight: Chunks carry rich metadata beyond just text —
    source pages, positions, ordering, and block types — enabling
    chunk-level inspection and source tracing.
    
    Source: rag/flow/chunker/token_chunker.py output format
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    text: str = ""
    token_count: int = 0
    chunk_order: int = 0
    source_pages: list[int] = field(default_factory=list)
    source_positions: list[dict] = field(default_factory=list)
    block_types: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    # For deduplication (RAGFlow pattern from task_service.py)
    content_hash: Optional[str] = None


@dataclass
class ChunkingConfig:
    """
    Configuration for the chunking strategy.
    
    RAGFlow Insight: These parameters are stored per Knowledge Base
    AND can be overridden per document. Different document types
    need different chunking strategies.
    
    Source: api/apps/kb_app.py parser_config schema
    """
    chunk_token_size: int = 512
    chunk_overlap_percent: int = 10
    delimiter: str = "\n"
    min_chunk_tokens: int = 50
    table_context_tokens: int = 100
    image_context_tokens: int = 100
    respect_block_boundaries: bool = True


@dataclass
class ProcessingResult:
    """Result of processing a single document through the full pipeline."""
    document_name: str
    file_type: str
    total_blocks: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    content_hash: str = ""
    chunks: list[Chunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
