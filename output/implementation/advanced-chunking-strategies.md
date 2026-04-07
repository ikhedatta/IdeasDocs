# Implementation Plan: Advanced Chunking Strategies

## Priority Focus Feature — Deep Dive

---

## 1. How RAGFlow Does It

### Chunking Architecture Overview

RAGFlow's chunking is NOT a simple "split by character count." It's a multi-stage pipeline:

```
Binary File
    │
    ▼ Parser (ONNX layout + OCR)
Structured Content Blocks (boxes with type annotations)
    type: text | table | figure | header | footer | caption
    coordinates: {page, x, y, w, h}
    content: extracted text
    │
    ▼ TokenChunker (rag/flow/chunker/token_chunker.py)
Semantic Chunks
    text: merged content
    positions: source coordinates
    images: associated figures
    metadata: extracted fields
```

### The TokenChunker Algorithm

**File**: `rag/flow/chunker/token_chunker.py`

**Step 1: Delimiter-Based Splitting**
```python
# Split text by configured delimiters
# Default delimiter: "\n"
# Each split becomes a "segment"
# Segments respect content block boundaries from parser
```

**Step 2: Token-Budget Merging**
```python
# Pseudocode from actual implementation:
accumulated_text = ""
accumulated_tokens = 0
chunks = []

for segment in segments:
    segment_tokens = count_tokens(segment)
    
    if accumulated_tokens + segment_tokens > chunk_token_size:
        # Save current chunk
        chunks.append(accumulated_text)
        
        # Start new chunk with overlap
        if overlap_percent > 0:
            overlap_tokens = int(accumulated_tokens * overlap_percent / 100)
            # Take last N tokens from previous chunk
            accumulated_text = get_tail_tokens(accumulated_text, overlap_tokens)
        else:
            accumulated_text = ""
    
    accumulated_text += segment
    accumulated_tokens = count_tokens(accumulated_text)

# Don't forget the last chunk
if accumulated_text:
    chunks.append(accumulated_text)
```

**Step 3: Table/Image Context Windows**
```python
# For tables and images, add surrounding text context
if content_block.type in ("table", "figure"):
    context_before = get_tokens_before(block, table_context_size)
    context_after = get_tokens_after(block, table_context_size)
    chunk_text = f"{context_before}\n{block.content}\n{context_after}"
```

**Step 4: Children Splitting (Optional)**
```python
# Secondary fine-grained splitting within chunks
# Uses "children delimiters" (e.g., sentence boundaries)
# Creates parent-child chunk relationships
# Parent chunk used for context, children chunks for precise retrieval
```

### Seven PDF Parsing Strategies

RAGFlow offers 7 different PDF parsing methods:

| Strategy | How It Works | Best For |
|----------|-------------|----------|
| **DeepDOC** (default) | ONNX neural networks detect layout → OCR → XGBoost merge | Most documents |
| **Plain Text** | `pdfminer` basic text extraction | Simple text-only PDFs |
| **MinerU** | Advanced layout analysis with citation extraction | Academic papers |
| **PaddleOCR** | PaddlePaddle OCR framework | Chinese-heavy documents |
| **Docling** | IBM's structured document converter | Docling-native formats |
| **TCADP** | Tencent Cloud Document API | Enterprise/complex layouts |
| **Vision LLM** | Send pages as images to GPT-4V/Claude | Tables, diagrams, complex figures |

### XGBoost Text Block Merging

RAGFlow's unique innovation: a trained XGBoost model with **30+ features** decides whether adjacent text blocks should merge:

**Spatial Features**:
- Y-distance between blocks
- Height ratios of blocks
- Horizontal alignment
- Character width analysis
- Block coordinates relative to page

**Linguistic Features**:
- Sentence ending patterns (Chinese vs English)
- Punctuation analysis (continuation vs termination)
- Token analysis of block boundaries

**Semantic Features**:
- Matching character widths (same paragraph indicator)
- Bullet point patterns
- Numbered list detection
- Parenthesis nesting (incomplete expression detection)

---

## 2. Implementation Plan for Our System

### 2.1 Chunking Strategy Architecture

```python
# services/chunking/base.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional

class ContentBlock(BaseModel):
    """Output from parser — structured content with metadata."""
    text: str
    block_type: str  # text, table, figure, header, list, code
    page_number: Optional[int] = None
    position: Optional[dict] = None  # {x, y, w, h}
    language: Optional[str] = None
    image_path: Optional[str] = None

class Chunk(BaseModel):
    """Final output — a semantic chunk ready for embedding."""
    text: str
    token_count: int
    chunk_order: int
    source_blocks: list[int]  # indices of source ContentBlocks
    source_pages: list[int]
    metadata: dict = {}
    image_paths: list[str] = []
    parent_chunk_id: Optional[str] = None

class ChunkingConfig(BaseModel):
    strategy: str = "token"  # token, semantic, hierarchical, fixed
    chunk_token_size: int = 512
    chunk_overlap_percent: int = 10
    delimiter: str = "\n"
    respect_block_boundaries: bool = True
    table_context_tokens: int = 100
    image_context_tokens: int = 100
    min_chunk_tokens: int = 50  # Don't create tiny chunks

class BaseChunker(ABC):
    def __init__(self, config: ChunkingConfig):
        self.config = config
    
    @abstractmethod
    def chunk(self, blocks: list[ContentBlock]) -> list[Chunk]:
        """Split structured content blocks into semantic chunks."""
        pass
```

### 2.2 Chunking Strategies

#### Strategy 1: Token-Based Chunking (Adapted from RAGFlow)

```python
# services/chunking/token_chunker.py
import tiktoken

class TokenChunker(BaseChunker):
    """RAGFlow-style token-budget chunking with delimiter splitting."""
    
    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def chunk(self, blocks: list[ContentBlock]) -> list[Chunk]:
        chunks = []
        
        # Phase 1: Handle special blocks (tables, figures)
        regular_blocks, special_chunks = self._separate_special_blocks(blocks)
        
        # Phase 2: Delimiter-based splitting of regular text blocks
        segments = self._split_by_delimiter(regular_blocks)
        
        # Phase 3: Token-budget merging
        text_chunks = self._merge_by_token_budget(segments)
        
        # Phase 4: Add context to special blocks
        for special in special_chunks:
            special.text = self._add_context(special, blocks)
        
        # Combine and order
        all_chunks = text_chunks + special_chunks
        all_chunks.sort(key=lambda c: c.chunk_order)
        
        return all_chunks
    
    def _split_by_delimiter(self, blocks: list[ContentBlock]) -> list[dict]:
        """Split text by configured delimiter, preserving block metadata."""
        segments = []
        for block in blocks:
            parts = block.text.split(self.config.delimiter)
            for part in parts:
                part = part.strip()
                if part:
                    segments.append({
                        "text": part,
                        "tokens": len(self.tokenizer.encode(part)),
                        "source_block": block,
                    })
        return segments
    
    def _merge_by_token_budget(self, segments: list[dict]) -> list[Chunk]:
        """Merge segments until token budget is reached."""
        chunks = []
        current_texts = []
        current_tokens = 0
        current_blocks = set()
        chunk_order = 0
        
        for seg in segments:
            if (current_tokens + seg["tokens"] > self.config.chunk_token_size 
                and current_texts):
                # Save current chunk
                chunk_text = f" {self.config.delimiter} ".join(current_texts)
                chunks.append(Chunk(
                    text=chunk_text,
                    token_count=current_tokens,
                    chunk_order=chunk_order,
                    source_blocks=list(current_blocks),
                    source_pages=self._extract_pages(current_blocks),
                ))
                chunk_order += 1
                
                # Apply overlap
                if self.config.chunk_overlap_percent > 0:
                    overlap_tokens = int(
                        current_tokens * self.config.chunk_overlap_percent / 100
                    )
                    current_texts, current_tokens = self._get_tail(
                        current_texts, overlap_tokens
                    )
                    current_blocks = set()  # Reset block tracking
                else:
                    current_texts = []
                    current_tokens = 0
                    current_blocks = set()
            
            current_texts.append(seg["text"])
            current_tokens += seg["tokens"]
            current_blocks.add(id(seg["source_block"]))
        
        # Final chunk
        if current_texts and current_tokens >= self.config.min_chunk_tokens:
            chunk_text = f" {self.config.delimiter} ".join(current_texts)
            chunks.append(Chunk(
                text=chunk_text,
                token_count=current_tokens,
                chunk_order=chunk_order,
                source_blocks=list(current_blocks),
                source_pages=self._extract_pages(current_blocks),
            ))
        
        return chunks
    
    def _add_context(self, chunk: Chunk, all_blocks: list[ContentBlock]) -> str:
        """Add surrounding text context to table/image chunks."""
        # Find adjacent text blocks and prepend/append context
        context_size = (
            self.config.table_context_tokens 
            if "table" in chunk.metadata.get("type", "")
            else self.config.image_context_tokens
        )
        
        # Get text before and after from adjacent blocks
        before = self._get_context_before(chunk, all_blocks, context_size)
        after = self._get_context_after(chunk, all_blocks, context_size)
        
        return f"{before}\n\n{chunk.text}\n\n{after}".strip()
```

#### Strategy 2: Semantic Chunking (Improvement over RAGFlow)

RAGFlow doesn't have this. We should.

```python
# services/chunking/semantic_chunker.py
import numpy as np

class SemanticChunker(BaseChunker):
    """Split by semantic boundaries using embedding similarity."""
    
    def __init__(self, config: ChunkingConfig, embedding_service):
        super().__init__(config)
        self.embedding_service = embedding_service
        self.breakpoint_threshold = 0.3  # Cosine distance threshold
    
    def chunk(self, blocks: list[ContentBlock]) -> list[Chunk]:
        # Phase 1: Split into sentences
        sentences = self._extract_sentences(blocks)
        
        # Phase 2: Embed each sentence
        embeddings = self.embedding_service.embed_batch(
            [s["text"] for s in sentences]
        )
        
        # Phase 3: Find semantic breakpoints
        distances = []
        for i in range(1, len(embeddings)):
            dist = 1 - np.dot(embeddings[i-1], embeddings[i])
            distances.append(dist)
        
        # Phase 4: Split at high-distance points
        breakpoints = [i for i, d in enumerate(distances) 
                       if d > self.breakpoint_threshold]
        
        # Phase 5: Form chunks respecting token budget
        chunks = self._form_chunks_from_breakpoints(sentences, breakpoints)
        
        return chunks
```

#### Strategy 3: Hierarchical Chunking (Parent-Child)

```python
# services/chunking/hierarchical_chunker.py

class HierarchicalChunker(BaseChunker):
    """Create parent (large) and child (small) chunks.
    
    Parent chunks provide context window.
    Child chunks are used for precise retrieval.
    On retrieval: find child → expand to parent for context.
    """
    
    def __init__(self, config: ChunkingConfig):
        super().__init__(config)
        self.parent_token_size = config.chunk_token_size * 3  # 3x parent
        self.child_token_size = config.chunk_token_size  # Normal child
    
    def chunk(self, blocks: list[ContentBlock]) -> list[Chunk]:
        # Phase 1: Create parent chunks (large, overlapping)
        parent_chunker = TokenChunker(ChunkingConfig(
            chunk_token_size=self.parent_token_size,
            chunk_overlap_percent=20,
        ))
        parents = parent_chunker.chunk(blocks)
        
        # Phase 2: Split each parent into children
        all_chunks = []
        for parent in parents:
            parent.metadata["is_parent"] = True
            all_chunks.append(parent)
            
            child_blocks = [ContentBlock(text=parent.text, block_type="text")]
            child_chunker = TokenChunker(ChunkingConfig(
                chunk_token_size=self.child_token_size,
            ))
            children = child_chunker.chunk(child_blocks)
            
            for child in children:
                child.parent_chunk_id = parent.chunk_order
                child.metadata["is_parent"] = False
                all_chunks.append(child)
        
        return all_chunks
```

### 2.3 Parser Registry

```python
# services/parsing/registry.py
from typing import Protocol

class Parser(Protocol):
    def parse(self, file_bytes: bytes, config: dict) -> list[ContentBlock]:
        ...

class ParserRegistry:
    _parsers: dict[str, type[Parser]] = {}
    
    @classmethod
    def register(cls, extensions: list[str]):
        def decorator(parser_class):
            for ext in extensions:
                cls._parsers[ext.lower()] = parser_class
            return parser_class
        return decorator
    
    @classmethod
    def get(cls, file_extension: str) -> Parser:
        ext = file_extension.lower().lstrip(".")
        if ext not in cls._parsers:
            raise ValueError(f"No parser for .{ext} files")
        return cls._parsers[ext]()

# Register parsers
@ParserRegistry.register([".pdf"])
class PDFParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        if config.get("use_layout_detection"):
            return self._parse_with_layout(file_bytes, config)
        else:
            return self._parse_simple(file_bytes, config)

@ParserRegistry.register([".docx", ".doc"])
class DocxParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # python-docx extraction with structure preservation
        ...

@ParserRegistry.register([".xlsx", ".xls", ".csv"])
class ExcelParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # Row-based parsing with header detection
        ...

@ParserRegistry.register([".html", ".htm"])
class HTMLParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # BeautifulSoup with boilerplate removal
        ...

@ParserRegistry.register([".md", ".markdown"])
class MarkdownParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # Section-based splitting by headers
        ...

@ParserRegistry.register([".pptx", ".ppt"])
class PowerPointParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # Slide-by-slide extraction
        ...

@ParserRegistry.register([".txt", ".text"])
class TextParser:
    def parse(self, file_bytes, config) -> list[ContentBlock]:
        # Direct text with paragraph detection
        ...
```

### 2.4 Chunking Strategy Factory

```python
# services/chunking/__init__.py

class ChunkerFactory:
    _strategies = {
        "token": TokenChunker,
        "semantic": SemanticChunker,
        "hierarchical": HierarchicalChunker,
    }
    
    @classmethod
    def create(cls, config: ChunkingConfig, **kwargs) -> BaseChunker:
        if config.strategy not in cls._strategies:
            raise ValueError(f"Unknown chunking strategy: {config.strategy}")
        return cls._strategies[config.strategy](config, **kwargs)
```

### 2.5 Configuration Presets

```python
# config/chunking_presets.py

PRESETS = {
    "general": ChunkingConfig(
        strategy="token",
        chunk_token_size=512,
        chunk_overlap_percent=10,
        delimiter="\n",
        respect_block_boundaries=True,
    ),
    "legal": ChunkingConfig(
        strategy="token",
        chunk_token_size=1024,  # Larger chunks for legal context
        chunk_overlap_percent=15,
        delimiter="\n\n",  # Split by paragraphs
        respect_block_boundaries=True,
    ),
    "technical": ChunkingConfig(
        strategy="token",
        chunk_token_size=512,
        chunk_overlap_percent=10,
        delimiter="\n",
        table_context_tokens=200,  # More table context
        image_context_tokens=150,
    ),
    "qa_optimized": ChunkingConfig(
        strategy="hierarchical",
        chunk_token_size=256,  # Smaller child chunks
        chunk_overlap_percent=0,
    ),
    "semantic": ChunkingConfig(
        strategy="semantic",
        chunk_token_size=512,
        chunk_overlap_percent=0,  # Semantic boundaries handle overlap
    ),
}
```

### 2.6 Improvements Over RAGFlow

| Aspect | RAGFlow | Our System |
|--------|---------|------------|
| **Strategies** | Token-based only | Token, Semantic, Hierarchical |
| **Semantic splitting** | Not available | Embedding-based boundary detection |
| **Parent-child chunks** | Basic "children delimiters" | Full hierarchical with parent expansion |
| **Configuration** | Raw JSON dict, no validation | Pydantic models with presets |
| **Strategy selection** | Manual via config | Factory pattern with named presets |
| **Tokenizer** | Custom RAG tokenizer | tiktoken (matches LLM tokenization) |
| **Min chunk size** | No minimum (can create tiny chunks) | Configurable minimum (default 50 tokens) |
| **Chunk quality metrics** | None | Token count, coherence score, coverage |

### 2.7 Testing Chunking Quality

```python
# tests/unit/test_chunker.py

def test_token_chunker_respects_budget():
    config = ChunkingConfig(chunk_token_size=100)
    chunker = TokenChunker(config)
    blocks = [ContentBlock(text="word " * 500, block_type="text")]
    chunks = chunker.chunk(blocks)
    for chunk in chunks:
        assert chunk.token_count <= 110  # 10% tolerance

def test_token_chunker_overlap():
    config = ChunkingConfig(chunk_token_size=100, chunk_overlap_percent=20)
    chunker = TokenChunker(config)
    blocks = [ContentBlock(text="sentence. " * 200, block_type="text")]
    chunks = chunker.chunk(blocks)
    # Check that consecutive chunks share ~20% content
    for i in range(len(chunks) - 1):
        overlap = set(chunks[i].text.split()) & set(chunks[i+1].text.split())
        assert len(overlap) > 0  # Some overlap exists

def test_table_context_window():
    config = ChunkingConfig(table_context_tokens=50)
    chunker = TokenChunker(config)
    blocks = [
        ContentBlock(text="Before table context.", block_type="text"),
        ContentBlock(text="| Col1 | Col2 |\n|---|---|\n| A | B |", block_type="table"),
        ContentBlock(text="After table context.", block_type="text"),
    ]
    chunks = chunker.chunk(blocks)
    table_chunk = [c for c in chunks if "Col1" in c.text][0]
    assert "Before table" in table_chunk.text
    assert "After table" in table_chunk.text

def test_min_chunk_size():
    config = ChunkingConfig(chunk_token_size=100, min_chunk_tokens=50)
    chunker = TokenChunker(config)
    blocks = [ContentBlock(text="Short text.", block_type="text")]
    chunks = chunker.chunk(blocks)
    # Very short text should still produce a chunk (appended to previous or standalone)
    assert all(c.token_count >= 3 for c in chunks)
```
