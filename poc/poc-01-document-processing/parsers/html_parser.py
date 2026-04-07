"""
HTML Parser using BeautifulSoup.

RAGFlow Source: deepdoc/parser/html_parser.py
Extracts structured content with boilerplate removal.
"""

from bs4 import BeautifulSoup, Comment
from chunkers.models import ContentBlock, BlockType
from .base import ParserRegistry


@ParserRegistry.register([".html", ".htm"])
class HTMLParser:
    """
    HTML parser with boilerplate removal and structure preservation.
    
    Detects: headings (h1-h6), tables, code blocks, lists, paragraphs.
    Removes: nav, footer, sidebar, script, style elements.
    """

    # Elements to remove (boilerplate)
    REMOVE_ELEMENTS = {
        "script", "style", "nav", "footer", "header",
        "aside", "form", "iframe", "noscript",
    }
    # Elements that indicate boilerplate by class/id
    BOILERPLATE_PATTERNS = {
        "sidebar", "navigation", "menu", "footer",
        "advertisement", "cookie", "popup", "modal",
    }

    def parse(
        self, file_bytes: bytes, filename: str, config: dict | None = None
    ) -> list[ContentBlock]:
        html_text = file_bytes.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html_text, "lxml")

        # Remove boilerplate elements
        self._remove_boilerplate(soup)

        blocks: list[ContentBlock] = []
        body = soup.find("body") or soup

        self._extract_blocks(body, blocks)
        return blocks

    def _remove_boilerplate(self, soup: BeautifulSoup):
        """Remove nav, scripts, ads, and other non-content elements."""
        # Remove by tag name
        for tag_name in self.REMOVE_ELEMENTS:
            for element in soup.find_all(tag_name):
                element.decompose()

        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove elements with boilerplate class/id patterns
        for element in soup.find_all(True):
            classes = " ".join(element.get("class", []))
            el_id = element.get("id", "")
            combined = f"{classes} {el_id}".lower()
            if any(pattern in combined for pattern in self.BOILERPLATE_PATTERNS):
                element.decompose()

    def _extract_blocks(self, element, blocks: list[ContentBlock]):
        """Recursively extract content blocks from HTML elements."""
        for child in element.children:
            if not hasattr(child, "name") or child.name is None:
                # Text node
                text = child.strip() if isinstance(child, str) else ""
                if text:
                    blocks.append(ContentBlock(text=text, block_type=BlockType.TEXT))
                continue

            tag = child.name.lower()

            # Headings
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                text = child.get_text(strip=True)
                if text:
                    blocks.append(ContentBlock(
                        text=text,
                        block_type=BlockType.HEADER,
                        metadata={"level": int(tag[1])},
                    ))

            # Tables
            elif tag == "table":
                table_text = self._table_to_text(child)
                if table_text.strip():
                    blocks.append(ContentBlock(
                        text=table_text,
                        block_type=BlockType.TABLE,
                    ))

            # Code blocks
            elif tag == "pre" or (tag == "code" and child.parent.name != "pre"):
                text = child.get_text()
                if text.strip():
                    blocks.append(ContentBlock(
                        text=text.strip(),
                        block_type=BlockType.CODE,
                    ))

            # Lists
            elif tag in ("ul", "ol"):
                text = self._list_to_text(child)
                if text.strip():
                    blocks.append(ContentBlock(
                        text=text,
                        block_type=BlockType.LIST,
                    ))

            # Paragraphs and divs
            elif tag in ("p", "div", "section", "article", "main"):
                if tag == "p":
                    text = child.get_text(strip=True)
                    if text:
                        blocks.append(ContentBlock(
                            text=text,
                            block_type=BlockType.TEXT,
                        ))
                else:
                    # Recurse into container elements
                    self._extract_blocks(child, blocks)

    def _table_to_text(self, table_element) -> str:
        """Convert HTML table to markdown-style text."""
        rows = []
        for tr in table_element.find_all("tr"):
            cells = []
            for cell in tr.find_all(["td", "th"]):
                cells.append(cell.get_text(strip=True).replace("|", "\\|"))
            if cells:
                rows.append("| " + " | ".join(cells) + " |")

        if len(rows) > 1:
            num_cols = rows[0].count("|") - 1
            header_sep = "| " + " | ".join(["---"] * max(num_cols, 1)) + " |"
            rows.insert(1, header_sep)

        return "\n".join(rows)

    def _list_to_text(self, list_element) -> str:
        """Convert HTML list to text with markers."""
        items = []
        is_ordered = list_element.name == "ol"
        for i, li in enumerate(list_element.find_all("li", recursive=False)):
            marker = f"{i + 1}." if is_ordered else "•"
            items.append(f"{marker} {li.get_text(strip=True)}")
        return "\n".join(items)
