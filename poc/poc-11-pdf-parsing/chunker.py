"""Chunking — split extracted text into embedding-ready chunks.

Phase 4: Takes the reading-order-sorted text boxes and produces
semantically meaningful chunks with token bounds and overlap.

Inspired by RAGFlow's TokenChunker:
1. Split text by delimiter patterns (sentence boundaries)
2. Merge segments until token budget is reached
3. Apply overlap from previous chunk
4. Preserve position metadata per chunk
"""

from __future__ import annotations

import logging
import re
from typing import Iterator

from config import CHUNK_DELIMITERS, CHUNK_OVERLAP_TOKENS, CHUNK_SIZE_TOKENS
from models import Chunk, ChunkType, LayoutType, TextBox

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Estimate token count (whitespace-split approximation).

    Production should use tiktoken or the actual tokenizer.
    Rule of thumb: 1 token ≈ 0.75 words for English.
    """
    words = text.split()
    return max(1, int(len(words) / 0.75))


def split_by_delimiters(text: str, pattern: str | None = None) -> list[str]:
    """Split text by delimiter pattern, preserving delimiters in segments.

    Mirrors RAGFlow's `_split_text_by_pattern()`.
    """
    if not text.strip():
        return []

    if pattern is None:
        pattern = CHUNK_DELIMITERS

    # Split but keep the delimiter attached to the preceding segment.
    # re.split with a capture group returns [text, delim, text, delim, ...].
    # Odd-indexed elements are the matched delimiters.
    parts = re.split(f"({pattern})", text)
    segments = []
    current = ""
    for i, part in enumerate(parts):
        current += part
        is_delimiter = i % 2 == 1  # Odd indices are captured groups
        if is_delimiter:
            if current.strip():
                segments.append(current)
            current = ""
    if current.strip():
        segments.append(current)

    return segments if segments else [text]


def chunk_text_boxes(
    text_boxes: list[TextBox],
    document_id: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """Create chunks from sorted text boxes.

    Strategy:
    1. Group consecutive boxes by layout context (titles create boundaries)
    2. Within each group, split by sentence delimiters
    3. Merge segments into chunks up to token budget
    4. Apply overlap from tail of previous chunk
    5. Track source positions for each chunk

    Args:
        text_boxes: Reading-order-sorted text boxes.
        document_id: Parent document ID.
        chunk_size: Max tokens per chunk (default: config.CHUNK_SIZE_TOKENS).
        chunk_overlap: Overlap tokens (default: config.CHUNK_OVERLAP_TOKENS).
    """
    if chunk_size is None:
        chunk_size = CHUNK_SIZE_TOKENS
    if chunk_overlap is None:
        chunk_overlap = CHUNK_OVERLAP_TOKENS

    chunks: list[Chunk] = []
    chunk_index = 0

    # Group text boxes into semantic sections (split on titles)
    sections = _group_into_sections(text_boxes)

    previous_tail = ""  # Overlap from previous chunk

    for section_boxes in sections:
        # Determine chunk type from first box's layout
        first_layout = section_boxes[0].layout_type if section_boxes else LayoutType.TEXT
        c_type = _layout_to_chunk_type(first_layout)

        # Combine text from all boxes in this section
        full_text = " ".join(b.text for b in section_boxes if b.text.strip())
        if not full_text.strip():
            continue

        # Collect positions from all boxes
        all_positions = [
            {"page": b.bbox.page, "x0": b.bbox.x0, "y0": b.bbox.y0,
             "x1": b.bbox.x1, "y1": b.bbox.y1}
            for b in section_boxes
        ]

        # Split into segments by delimiters
        segments = split_by_delimiters(full_text)

        # Merge segments into chunks
        current_text = previous_tail
        current_tokens = estimate_tokens(current_text)
        current_positions = list(all_positions) if current_text else []

        for segment in segments:
            seg_tokens = estimate_tokens(segment)

            if current_tokens + seg_tokens > chunk_size and current_text.strip():
                # Emit current chunk
                chunks.append(Chunk(
                    document_id=document_id,
                    content=current_text.strip(),
                    chunk_type=c_type,
                    token_count=current_tokens,
                    chunk_index=chunk_index,
                    positions=current_positions[:],
                    metadata={
                        "section_title": _find_section_title(section_boxes),
                    },
                ))
                chunk_index += 1

                # Compute overlap tail from current chunk
                previous_tail = _extract_tail(current_text, chunk_overlap)
                current_text = previous_tail + " " + segment if previous_tail else segment
                current_tokens = estimate_tokens(current_text)
                current_positions = list(all_positions)
            else:
                if current_text:
                    current_text += " " + segment
                else:
                    current_text = segment
                current_tokens += seg_tokens
                if not current_positions:
                    current_positions = list(all_positions)

        # Emit remaining text
        if current_text.strip():
            chunks.append(Chunk(
                document_id=document_id,
                content=current_text.strip(),
                chunk_type=c_type,
                token_count=estimate_tokens(current_text),
                chunk_index=chunk_index,
                positions=current_positions[:],
                metadata={
                    "section_title": _find_section_title(section_boxes),
                },
            ))
            chunk_index += 1
            previous_tail = _extract_tail(current_text, chunk_overlap)

    logger.info(
        "Created %d chunks from %d text boxes (avg %d tokens/chunk)",
        len(chunks),
        len(text_boxes),
        sum(c.token_count for c in chunks) // max(len(chunks), 1),
    )
    return chunks


# ── Helpers ────────────────────────────────────────────────────────────

def _group_into_sections(text_boxes: list[TextBox]) -> list[list[TextBox]]:
    """Group text boxes into sections, splitting at title boundaries.

    Each title starts a new section. Body text, list items, etc.
    continue the current section.
    """
    if not text_boxes:
        return []

    sections: list[list[TextBox]] = []
    current: list[TextBox] = []

    for box in text_boxes:
        if box.layout_type == LayoutType.TITLE and current:
            # Title starts a new section
            sections.append(current)
            current = [box]
        elif box.layout_type in (LayoutType.HEADER, LayoutType.FOOTER):
            # Skip headers/footers from main content
            continue
        else:
            current.append(box)

    if current:
        sections.append(current)

    return sections


def _layout_to_chunk_type(layout: LayoutType) -> ChunkType:
    """Map layout type to chunk type."""
    if layout == LayoutType.TABLE:
        return ChunkType.TABLE
    if layout == LayoutType.FIGURE:
        return ChunkType.FIGURE
    if layout == LayoutType.TITLE:
        return ChunkType.TITLE
    return ChunkType.TEXT


def _find_section_title(boxes: list[TextBox]) -> str:
    """Find the title text from a section's boxes."""
    for box in boxes:
        if box.layout_type == LayoutType.TITLE:
            return box.text.strip()
    return ""


def _extract_tail(text: str, overlap_tokens: int) -> str:
    """Extract the last N tokens from text for overlap."""
    if overlap_tokens <= 0:
        return ""
    words = text.split()
    # Approximate: 1 token ≈ 0.75 words
    word_count = int(overlap_tokens * 0.75)
    if word_count >= len(words):
        return text
    return " ".join(words[-word_count:])
