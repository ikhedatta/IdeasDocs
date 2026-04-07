# parsers package — auto-import all parsers to trigger registration
from .base import ParserRegistry
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .html_parser import HTMLParser
from .markdown_parser import MarkdownParser

__all__ = ["ParserRegistry", "PDFParser", "DocxParser", "HTMLParser", "MarkdownParser"]
