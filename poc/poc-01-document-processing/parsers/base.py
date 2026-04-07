"""
Parser base protocol and registry.

RAGFlow Pattern (from deepdoc/parser/):
- Each document format has a dedicated parser class
- All parsers produce the same output: List[ContentBlock]
- A registry maps file extensions to parser classes
- New formats are added by registering a new parser class

This enables the pipeline to handle any document format
without changing the chunking or embedding code.
"""

from typing import Protocol
from chunkers.models import ContentBlock


class Parser(Protocol):
    """Protocol that all document parsers must implement."""

    def parse(self, file_bytes: bytes, filename: str, config: dict | None = None) -> list[ContentBlock]:
        """
        Parse a document into structured content blocks.
        
        Args:
            file_bytes: Raw file content
            filename: Original filename (for format detection)
            config: Optional parser-specific configuration
            
        Returns:
            List of ContentBlock objects with type annotations
        """
        ...


class ParserRegistry:
    """
    Registry mapping file extensions to parser classes.
    
    RAGFlow Pattern: deepdoc/parser/ has 16 specialized parsers,
    each registered for specific extensions. The pipeline selects
    the right parser based on file extension.
    
    Usage:
        @ParserRegistry.register([".pdf"])
        class PDFParser:
            def parse(self, file_bytes, filename, config=None):
                ...
        
        parser = ParserRegistry.get(".pdf")
        blocks = parser.parse(file_bytes, "doc.pdf")
    """

    _parsers: dict[str, type] = {}

    @classmethod
    def register(cls, extensions: list[str]):
        """Decorator to register a parser for given file extensions."""
        def decorator(parser_class):
            for ext in extensions:
                cls._parsers[ext.lower()] = parser_class
            return parser_class
        return decorator

    @classmethod
    def get(cls, extension: str) -> "Parser":
        """Get a parser instance for the given file extension."""
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        if ext not in cls._parsers:
            supported = ", ".join(sorted(cls._parsers.keys()))
            raise ValueError(
                f"No parser registered for '{ext}'. Supported: {supported}"
            )
        return cls._parsers[ext]()

    @classmethod
    def supported_extensions(cls) -> list[str]:
        """List all registered file extensions."""
        return sorted(cls._parsers.keys())
