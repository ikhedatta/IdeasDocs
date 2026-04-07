"""
Markdown Parser — section-based splitting by headers.

RAGFlow Source: deepdoc/parser/markdown_parser.py
"""

import re
from chunkers.models import ContentBlock, BlockType
from .base import ParserRegistry


@ParserRegistry.register([".md", ".markdown", ".txt", ".text"])
class MarkdownParser:
    """
    Markdown/text parser with header-based structure detection.
    
    Supports: headers (#), code blocks (```), tables (|), lists (- / *).
    Plain text files (.txt) are treated as unstructured text blocks.
    """

    def parse(
        self, file_bytes: bytes, filename: str, config: dict | None = None
    ) -> list[ContentBlock]:
        text = file_bytes.decode("utf-8", errors="replace")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext in ("txt", "text"):
            return self._parse_plain_text(text)
        return self._parse_markdown(text)

    def _parse_markdown(self, text: str) -> list[ContentBlock]:
        """Parse markdown with structure detection."""
        blocks: list[ContentBlock] = []
        lines = text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Code block (```)
            if line.strip().startswith("```"):
                code_lines = []
                lang = line.strip()[3:].strip()
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if code_lines:
                    blocks.append(ContentBlock(
                        text="\n".join(code_lines),
                        block_type=BlockType.CODE,
                        metadata={"language": lang} if lang else {},
                    ))
                i += 1
                continue

            # Header (#)
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
            if header_match:
                level = len(header_match.group(1))
                blocks.append(ContentBlock(
                    text=header_match.group(2).strip(),
                    block_type=BlockType.HEADER,
                    metadata={"level": level},
                ))
                i += 1
                continue

            # Table (|)
            if "|" in line and line.strip().startswith("|"):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i])
                    i += 1
                if table_lines:
                    blocks.append(ContentBlock(
                        text="\n".join(table_lines),
                        block_type=BlockType.TABLE,
                    ))
                continue

            # List (- / * / 1.)
            if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
                list_lines = [line]
                i += 1
                while i < len(lines) and (
                    re.match(r"^\s*[-*+]\s+", lines[i]) or
                    re.match(r"^\s*\d+[.)]\s+", lines[i]) or
                    (lines[i].startswith("  ") and lines[i].strip())
                ):
                    list_lines.append(lines[i])
                    i += 1
                blocks.append(ContentBlock(
                    text="\n".join(list_lines),
                    block_type=BlockType.LIST,
                ))
                continue

            # Regular text paragraph (collect contiguous non-empty lines)
            if line.strip():
                para_lines = [line]
                i += 1
                while i < len(lines) and lines[i].strip() and not (
                    lines[i].strip().startswith("#") or
                    lines[i].strip().startswith("```") or
                    lines[i].strip().startswith("|")
                ):
                    para_lines.append(lines[i])
                    i += 1
                blocks.append(ContentBlock(
                    text="\n".join(para_lines),
                    block_type=BlockType.TEXT,
                ))
                continue

            i += 1  # Skip empty lines

        return blocks

    def _parse_plain_text(self, text: str) -> list[ContentBlock]:
        """Parse plain text by splitting on double newlines (paragraphs)."""
        paragraphs = re.split(r"\n\s*\n", text)
        blocks = []
        for para in paragraphs:
            para = para.strip()
            if para:
                blocks.append(ContentBlock(
                    text=para,
                    block_type=BlockType.TEXT,
                ))
        return blocks
