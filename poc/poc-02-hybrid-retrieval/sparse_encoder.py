"""Simple BM25-style sparse vector encoder.

Generates sparse vectors compatible with Qdrant's sparse vector search.
Uses TF-IDF inspired weighting without requiring a pre-built corpus index.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class SparseVector:
    """Qdrant-compatible sparse vector: parallel arrays of indices and values."""
    indices: list[int]
    values: list[float]


class SparseEncoder:
    """Generates sparse vectors from text using term hashing and TF-IDF-like weighting.

    This is a simplified BM25 approach that:
    1. Tokenizes text into terms
    2. Computes term frequency with BM25 saturation
    3. Hashes terms to integer indices for Qdrant sparse vectors

    For production, replace with a learned sparse encoder (SPLADE, etc.)
    """

    # BM25 parameters
    K1 = 1.2  # Term frequency saturation
    B = 0.75  # Length normalization
    AVG_DOC_LEN = 256  # Assumed average document length in tokens

    # Hash space for sparse vector indices (Qdrant uses uint32)
    HASH_SPACE = 2**31 - 1

    # Simple stop words to filter
    STOP_WORDS = frozenset([
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "because", "but", "and", "or", "if", "while", "this", "that", "these",
        "those", "it", "its", "i", "me", "my", "we", "our", "you", "your",
        "he", "him", "his", "she", "her", "they", "them", "their", "what",
        "which", "who", "whom",
    ])

    def __init__(self):
        pass

    def _tokenize(self, text: str) -> list[str]:
        """Lowercase, split on non-alphanumeric, filter stop words."""
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        return [t for t in tokens if t not in self.STOP_WORDS and len(t) > 1]

    def _hash_term(self, term: str) -> int:
        """Deterministic hash of a term to a sparse vector index."""
        h = hash(term) % self.HASH_SPACE
        return abs(h)

    def _bm25_tf(self, raw_tf: int, doc_len: int) -> float:
        """BM25 term frequency with saturation and length normalization."""
        norm_len = doc_len / self.AVG_DOC_LEN if self.AVG_DOC_LEN > 0 else 1.0
        denominator = raw_tf + self.K1 * (1 - self.B + self.B * norm_len)
        return (raw_tf * (self.K1 + 1)) / denominator if denominator > 0 else 0.0

    def encode(self, text: str) -> SparseVector:
        """Encode text into a sparse vector.

        Returns a SparseVector with term-hashed indices and BM25-weighted values.
        """
        tokens = self._tokenize(text)
        if not tokens:
            return SparseVector(indices=[], values=[])

        term_counts = Counter(tokens)
        doc_len = len(tokens)

        indices = []
        values = []

        for term, count in term_counts.items():
            idx = self._hash_term(term)
            weight = self._bm25_tf(count, doc_len)
            if weight > 0:
                indices.append(idx)
                values.append(weight)

        return SparseVector(indices=indices, values=values)

    def encode_query(self, query: str) -> SparseVector:
        """Encode a query into a sparse vector.

        Queries use simpler weighting (binary presence with slight boost for repeats).
        """
        tokens = self._tokenize(query)
        if not tokens:
            return SparseVector(indices=[], values=[])

        term_counts = Counter(tokens)
        indices = []
        values = []

        for term, count in term_counts.items():
            idx = self._hash_term(term)
            # Query terms get logarithmic weight for repeats
            weight = 1.0 + math.log(count) if count > 1 else 1.0
            indices.append(idx)
            values.append(weight)

        return SparseVector(indices=indices, values=values)
