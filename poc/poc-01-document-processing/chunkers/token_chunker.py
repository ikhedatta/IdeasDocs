"""
Token-Budget Chunker — Core chunking algorithm adapted from RAGFlow.

RAGFlow Source: rag/flow/chunker/token_chunker.py

Algorithm (two-stage):
1. Delimiter-based splitting: Split text by configured delimiters (newlines, custom)
2. Token-budget merging: Accumulate segments until token budget reached, then emit chunk
3. Overlap: Include last N% tokens from previous chunk in next chunk
4. Special handling: Tables/images wrapped with surrounding context text

Key Insight from RAGFlow: The chunker respects content block boundaries from the parser.
Tables are never split — they're treated as atomic units with surrounding context.
"""

import tiktoken
from .models import ContentBlock, Chunk, ChunkingConfig, BlockType


class TokenChunker:
    """
    Token-budget chunking with delimiter splitting and overlap.
    
    This implements RAGFlow's core chunking pattern:
    - First split by delimiters (respecting structure)
    - Then merge segments up to token budget
    - Apply configurable overlap between chunks
    - Wrap tables/images with surrounding context
    """

    def __init__(self, config: ChunkingConfig | None = None):
        self.config = config or ChunkingConfig()
        # Use tiktoken for accurate token counting (matches OpenAI models)
        # RAGFlow uses its own tokenizer; we use tiktoken for consistency
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken encoder."""
        if not text:
            return 0
        return len(self.encoder.encode(text))

    def chunk(self, blocks: list[ContentBlock]) -> list[Chunk]:
        """
        Main entry point: convert structured content blocks into semantic chunks.
        
        Flow (adapted from RAGFlow's TokenChunker):
        1. Separate special blocks (tables, figures) from regular text
        2. Split regular text by delimiters
        3. Merge splits by token budget with overlap
        4. Add context to special blocks
        5. Interleave everything in document order
        """
        if not blocks:
            return []

        # Phase 1: Separate special blocks (tables, figures)
        regular_segments = []
        special_blocks = []
        
        for i, block in enumerate(blocks):
            if block.block_type in (BlockType.TABLE, BlockType.FIGURE):
                special_blocks.append((i, block))
            else:
                # Split regular text blocks by delimiter
                parts = block.text.split(self.config.delimiter)
                for part in parts:
                    part = part.strip()
                    if part:
                        regular_segments.append({
                            "text": part,
                            "tokens": self.count_tokens(part),
                            "block_index": i,
                            "block": block,
                        })

        # Phase 2: Merge regular segments by token budget
        text_chunks = self._merge_by_token_budget(regular_segments)

        # Phase 3: Add context to special blocks
        special_chunks = self._process_special_blocks(special_blocks, blocks)

        # Phase 4: Combine and sort by order
        all_chunks = text_chunks + special_chunks
        all_chunks.sort(key=lambda c: c.chunk_order)
        
        # Reassign sequential order
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_order = i

        return all_chunks

    def _merge_by_token_budget(self, segments: list[dict]) -> list[Chunk]:
        """
        Merge text segments until token budget is reached.
        
        RAGFlow Pattern (from token_chunker.py):
        - Accumulate segments until chunk_token_size exceeded
        - Save accumulated text as chunk
        - Apply overlap by keeping tail tokens from previous chunk
        - Track source pages and positions throughout
        """
        if not segments:
            return []

        chunks = []
        current_texts: list[str] = []
        current_tokens = 0
        current_pages: set[int] = set()
        current_positions: list[dict] = []
        current_block_types: set[str] = set()
        chunk_order = 0

        for seg in segments:
            # Would this segment overflow the budget?
            if current_tokens + seg["tokens"] > self.config.chunk_token_size and current_texts:
                # Emit current chunk
                chunk_text = ("\n" if self.config.delimiter == "\n" else " ").join(current_texts)
                chunks.append(Chunk(
                    text=chunk_text,
                    token_count=current_tokens,
                    chunk_order=chunk_order,
                    source_pages=sorted(current_pages),
                    source_positions=current_positions.copy(),
                    block_types=list(current_block_types),
                ))
                chunk_order += 1

                # Apply overlap (RAGFlow pattern from token_chunker.py)
                if self.config.chunk_overlap_percent > 0:
                    overlap_tokens = int(
                        current_tokens * self.config.chunk_overlap_percent / 100
                    )
                    current_texts, current_tokens = self._get_tail_segments(
                        current_texts, overlap_tokens
                    )
                else:
                    current_texts = []
                    current_tokens = 0

                current_pages = set()
                current_positions = []
                current_block_types = set()

            # Add segment to accumulator
            current_texts.append(seg["text"])
            current_tokens += seg["tokens"]
            
            block = seg["block"]
            if block.page_number is not None:
                current_pages.add(block.page_number)
            if block.position:
                current_positions.append(block.position)
            current_block_types.add(block.block_type.value)

        # Emit final chunk (if meets minimum threshold)
        if current_texts and current_tokens >= self.config.min_chunk_tokens:
            chunk_text = ("\n" if self.config.delimiter == "\n" else " ").join(current_texts)
            chunks.append(Chunk(
                text=chunk_text,
                token_count=current_tokens,
                chunk_order=chunk_order,
                source_pages=sorted(current_pages),
                source_positions=current_positions,
                block_types=list(current_block_types),
            ))
        elif current_texts and chunks:
            # Append tiny leftover to last chunk
            last_chunk = chunks[-1]
            extra_text = ("\n" if self.config.delimiter == "\n" else " ").join(current_texts)
            last_chunk.text += "\n" + extra_text
            last_chunk.token_count += current_tokens

        return chunks

    def _get_tail_segments(
        self, texts: list[str], target_tokens: int
    ) -> tuple[list[str], int]:
        """
        Get the tail N tokens worth of segments for overlap.
        
        RAGFlow Pattern: The overlap takes from the END of the previous chunk
        to create continuity in the next chunk.
        """
        if target_tokens <= 0:
            return [], 0

        tail_texts = []
        tail_tokens = 0

        for text in reversed(texts):
            t = self.count_tokens(text)
            if tail_tokens + t > target_tokens:
                break
            tail_texts.insert(0, text)
            tail_tokens += t

        return tail_texts, tail_tokens

    def _process_special_blocks(
        self, special_blocks: list[tuple[int, ContentBlock]], all_blocks: list[ContentBlock]
    ) -> list[Chunk]:
        """
        Process tables and figures as atomic units with surrounding context.
        
        RAGFlow Pattern (from token_chunker.py):
        - Tables are never split across chunks
        - Each table/figure gets N tokens of surrounding text for context
        - This prevents orphaned tables that lose meaning without context
        """
        chunks = []

        for block_index, block in special_blocks:
            context_tokens = (
                self.config.table_context_tokens
                if block.block_type == BlockType.TABLE
                else self.config.image_context_tokens
            )

            # Get text before this block
            before_text = self._get_context_text(all_blocks, block_index, direction="before", max_tokens=context_tokens)
            # Get text after this block
            after_text = self._get_context_text(all_blocks, block_index, direction="after", max_tokens=context_tokens)

            # Combine: context_before + table/figure + context_after
            parts = [p for p in [before_text, block.text, after_text] if p]
            chunk_text = "\n\n".join(parts)

            chunks.append(Chunk(
                text=chunk_text,
                token_count=self.count_tokens(chunk_text),
                chunk_order=block_index,  # Will be re-sorted later
                source_pages=[block.page_number] if block.page_number else [],
                source_positions=[block.position] if block.position else [],
                block_types=[block.block_type.value],
                metadata={"has_context": True, "original_type": block.block_type.value},
            ))

        return chunks

    def _get_context_text(
        self, blocks: list[ContentBlock], target_index: int, direction: str, max_tokens: int
    ) -> str:
        """Get surrounding text blocks up to max_tokens for context."""
        if max_tokens <= 0:
            return ""

        context_parts = []
        token_count = 0

        if direction == "before":
            indices = range(target_index - 1, -1, -1)
        else:
            indices = range(target_index + 1, len(blocks))

        for i in indices:
            block = blocks[i]
            if block.block_type in (BlockType.TABLE, BlockType.FIGURE):
                continue  # Skip other special blocks
            tokens = self.count_tokens(block.text)
            if token_count + tokens > max_tokens:
                break
            context_parts.append(block.text)
            token_count += tokens

        if direction == "before":
            context_parts.reverse()

        return " ".join(context_parts)
