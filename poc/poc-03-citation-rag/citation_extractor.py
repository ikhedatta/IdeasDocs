"""Citation extraction and validation from LLM output.

Parses [n] citations from generated text, maps them to source chunks,
and validates that all claims are properly cited.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Citation:
    """A single citation reference."""
    index: int  # The [n] number
    document_name: str = ""
    document_id: str = ""
    chunk_id: str = ""
    chunk_content: str = ""
    score: float = 0.0


@dataclass
class CitationResult:
    """Full citation analysis of an LLM response."""
    answer: str
    citations: list[Citation] = field(default_factory=list)
    cited_indices: set[int] = field(default_factory=set)
    available_indices: set[int] = field(default_factory=set)
    confidence: str = "grounded"  # "grounded", "partial", "no_context"

    @property
    def citation_coverage(self) -> float:
        """Fraction of sentences that contain citations."""
        sentences = [s.strip() for s in re.split(r'[.!?]\s', self.answer) if s.strip()]
        if not sentences:
            return 0.0
        cited = sum(1 for s in sentences if re.search(r'\[\d+\]', s))
        return cited / len(sentences)

    @property
    def unused_sources(self) -> set[int]:
        """Source indices that were available but not cited."""
        return self.available_indices - self.cited_indices

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [
                {
                    "index": c.index,
                    "document_name": c.document_name,
                    "document_id": c.document_id,
                    "chunk_id": c.chunk_id,
                    "content_preview": c.chunk_content[:100] + "..." if len(c.chunk_content) > 100 else c.chunk_content,
                    "score": round(c.score, 4),
                }
                for c in self.citations
            ],
            "confidence": self.confidence,
            "citation_coverage": round(self.citation_coverage, 2),
            "cited_indices": sorted(self.cited_indices),
            "unused_sources": sorted(self.unused_sources),
        }


class CitationExtractor:
    """Extract and validate citations from LLM-generated text."""

    # Pattern for [n] or [n][m] citations
    CITATION_PATTERN = re.compile(r'\[(\d+)\]')

    # Patterns indicating the LLM admitted lack of knowledge
    NO_CONTEXT_PATTERNS = [
        r"cannot answer.*based on.*documents",
        r"do(?:es)? not contain.*information",
        r"no (?:relevant )?information.*(?:found|available)",
        r"not (?:enough|sufficient) (?:information|context)",
        r"unable to (?:find|answer)",
    ]

    def extract(
        self,
        answer: str,
        source_chunks: list[dict],
    ) -> CitationResult:
        """Extract citations from LLM answer and map to source chunks.

        Args:
            answer: LLM-generated text with [n] citations
            source_chunks: List of dicts with keys: content, document_name,
                          document_id, chunk_id, score

        Returns:
            CitationResult with parsed citations and confidence assessment
        """
        available_indices = set(range(1, len(source_chunks) + 1))

        # Check for "I don't know" responses
        if self._is_no_context_response(answer):
            return CitationResult(
                answer=answer,
                citations=[],
                cited_indices=set(),
                available_indices=available_indices,
                confidence="no_context",
            )

        # Extract citation indices
        cited_indices = set()
        for match in self.CITATION_PATTERN.finditer(answer):
            idx = int(match.group(1))
            if idx in available_indices:
                cited_indices.add(idx)

        # Build citation objects
        citations = []
        for idx in sorted(cited_indices):
            chunk = source_chunks[idx - 1]  # 1-indexed to 0-indexed
            citations.append(
                Citation(
                    index=idx,
                    document_name=chunk.get("document_name", ""),
                    document_id=chunk.get("document_id", ""),
                    chunk_id=chunk.get("chunk_id", ""),
                    chunk_content=chunk.get("content", ""),
                    score=chunk.get("score", 0.0),
                )
            )

        # Assess confidence
        confidence = self._assess_confidence(answer, cited_indices, available_indices)

        return CitationResult(
            answer=answer,
            citations=citations,
            cited_indices=cited_indices,
            available_indices=available_indices,
            confidence=confidence,
        )

    def _is_no_context_response(self, answer: str) -> bool:
        """Check if the LLM response indicates no context was found."""
        answer_lower = answer.lower()
        return any(re.search(p, answer_lower) for p in self.NO_CONTEXT_PATTERNS)

    def _assess_confidence(
        self,
        answer: str,
        cited_indices: set[int],
        available_indices: set[int],
    ) -> str:
        """Assess citation confidence level."""
        if not cited_indices:
            # No citations found — likely hallucinated or very casual response
            return "no_context"

        # Count sentences with citations
        sentences = [s.strip() for s in re.split(r'[.!?]\s', answer) if len(s.strip()) > 20]
        if not sentences:
            return "grounded"

        cited_sentences = sum(1 for s in sentences if re.search(r'\[\d+\]', s))
        ratio = cited_sentences / len(sentences)

        if ratio >= 0.7:
            return "grounded"
        elif ratio >= 0.3:
            return "partial"
        else:
            return "no_context"
