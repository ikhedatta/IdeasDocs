"""
Document Processing Pipeline — orchestrates parse → chunk → embed → store.

RAGFlow Source: rag/flow/pipeline.py + api/db/services/task_service.py

This combines the parsing, chunking, embedding, and storage steps
into a single pipeline. In production, each step would be a Celery task.
"""

import os
import xxhash
from typing import Optional
from uuid import uuid4

from parsers import ParserRegistry
from chunkers import TokenChunker, ChunkingConfig, ProcessingResult
from embedding_service import EmbeddingService
from qdrant_store import QdrantStore


class DocumentPipeline:
    """
    Full document processing pipeline: parse → chunk → embed → store.
    
    RAGFlow Architecture:
    1. Parser converts binary → structured ContentBlocks
    2. TokenChunker splits blocks → semantic Chunks
    3. EmbeddingService embeds chunks in batches
    4. QdrantStore upserts vectors with metadata
    
    Key RAGFlow Patterns:
    - Content-hash deduplication (xxhash64 of config)
    - Per-KB embedding model (locked after first document)
    - Rich metadata preservation through entire pipeline
    """

    def __init__(
        self,
        embedding_model: str = "text-embedding-3-small",
        qdrant_url: str = "http://localhost:6333",
        embedding_api_key: Optional[str] = None,
    ):
        self.embedder = EmbeddingService(
            model=embedding_model,
            api_key=embedding_api_key,
        )
        self.store = QdrantStore(url=qdrant_url)
        self.embedding_model = embedding_model

    def _compute_config_hash(self, chunking_config: ChunkingConfig) -> str:
        """
        Compute config hash for task deduplication.
        
        RAGFlow Pattern (from task_service.py):
        xxhash64 of the chunking config produces a digest. If the same
        document was processed with the same config before, chunks can be reused.
        """
        config_str = (
            f"{chunking_config.chunk_token_size}:"
            f"{chunking_config.chunk_overlap_percent}:"
            f"{chunking_config.delimiter}:"
            f"{chunking_config.min_chunk_tokens}:"
            f"{self.embedding_model}"
        )
        return xxhash.xxh64(config_str.encode()).hexdigest()

    async def process(
        self,
        file_bytes: bytes,
        filename: str,
        kb_id: str,
        document_id: Optional[str] = None,
        chunking_config: Optional[ChunkingConfig] = None,
        parser_config: Optional[dict] = None,
    ) -> ProcessingResult:
        """
        Process a document through the full pipeline.
        
        Args:
            file_bytes: Raw file content
            filename: Original filename (for extension detection)
            kb_id: Knowledge Base ID (determines Qdrant collection)
            document_id: Optional document ID (auto-generated if not provided)
            chunking_config: Chunking parameters (defaults if not provided)
            parser_config: Parser-specific config (e.g., page_ranges for PDF)
            
        Returns:
            ProcessingResult with chunk count, token count, and errors
        """
        config = chunking_config or ChunkingConfig()
        doc_id = document_id or str(uuid4())
        collection_name = f"kb_{kb_id}"

        result = ProcessingResult(
            document_name=filename,
            file_type=self._get_extension(filename),
            content_hash=self._compute_config_hash(config),
        )

        # === Step 1: Parse ===
        try:
            extension = self._get_extension(filename)
            parser = ParserRegistry.get(extension)
            blocks = parser.parse(file_bytes, filename, parser_config)
            result.total_blocks = len(blocks)
        except Exception as e:
            result.errors.append(f"Parse error: {str(e)}")
            return result

        if not blocks:
            result.errors.append("No content blocks extracted from document")
            return result

        # === Step 2: Chunk ===
        try:
            chunker = TokenChunker(config)
            chunks = chunker.chunk(blocks)
            result.total_chunks = len(chunks)
        except Exception as e:
            result.errors.append(f"Chunking error: {str(e)}")
            return result

        if not chunks:
            result.errors.append("No chunks produced from content blocks")
            return result

        # === Step 3: Embed ===
        try:
            texts = [chunk.text for chunk in chunks]
            vectors = await self.embedder.embed_batch(texts)
            
            for chunk, vector in zip(chunks, vectors):
                chunk.embedding = vector
                
            dimension = self.embedder.get_dimension()
        except Exception as e:
            result.errors.append(f"Embedding error: {str(e)}")
            return result

        # === Step 4: Store in Qdrant ===
        try:
            # Ensure collection exists
            self.store.create_collection(collection_name, dimension=dimension)
            
            # Delete old chunks for this document (re-parse scenario)
            self.store.delete_by_document(collection_name, doc_id)
            
            # Upsert new chunks
            count = self.store.upsert_chunks(
                collection_name=collection_name,
                chunks=chunks,
                document_id=doc_id,
                document_name=filename,
                kb_id=kb_id,
            )
        except Exception as e:
            result.errors.append(f"Storage error: {str(e)}")
            return result

        # Compute totals
        result.total_tokens = sum(c.token_count for c in chunks)
        result.chunks = chunks

        return result

    def _get_extension(self, filename: str) -> str:
        """Extract file extension from filename."""
        if "." in filename:
            return "." + filename.rsplit(".", 1)[-1].lower()
        return ""


def process_sync(
    file_path: str,
    kb_id: str = "default",
    embedding_model: str = "text-embedding-3-small",
    qdrant_url: str = "http://localhost:6333",
    chunking_config: Optional[ChunkingConfig] = None,
) -> ProcessingResult:
    """
    Synchronous convenience wrapper for CLI usage.
    
    Usage:
        result = process_sync("document.pdf", kb_id="my-kb")
        print(f"Created {result.total_chunks} chunks")
    """
    import asyncio

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    filename = os.path.basename(file_path)
    pipeline = DocumentPipeline(
        embedding_model=embedding_model,
        qdrant_url=qdrant_url,
    )

    return asyncio.run(
        pipeline.process(
            file_bytes=file_bytes,
            filename=filename,
            kb_id=kb_id,
            chunking_config=chunking_config,
        )
    )
