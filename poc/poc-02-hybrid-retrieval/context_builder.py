"""Token-aware context builder.

Assembles retrieved chunks into a context string that fits within the LLM's
token budget. Implements the pattern from RAGFlow's rag/prompts/generator.py kb_prompt().
"""
import tiktoken

from config import SearchResult


class ContextBuilder:
    """Build LLM context from retrieved chunks, respecting token limits.

    Key behaviors (from RAGFlow):
    - Chunks are added in score order (best first)
    - Each chunk is numbered for citation reference
    - Stops adding when token budget is exhausted
    - Includes document attribution for each chunk
    """

    def __init__(self, max_tokens: int = 4096, model: str = "gpt-4"):
        self.max_tokens = max_tokens
        try:
            self.encoder = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoder = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    def build(
        self,
        results: list[SearchResult],
        separator: str = "\n---\n",
        include_metadata: bool = True,
    ) -> tuple[str, list[SearchResult]]:
        """Build context string from search results.

        Returns:
            (context_string, included_results): The assembled context and
            which results were actually included (may be fewer than input
            if token budget was reached).
        """
        if not results:
            return "", []

        used_tokens = 0
        included: list[SearchResult] = []
        context_parts: list[str] = []

        # Reserve tokens for separator overhead
        sep_tokens = self._count_tokens(separator)

        for i, result in enumerate(results):
            # Format chunk with citation number and source
            chunk_text = self._format_chunk(i + 1, result, include_metadata)
            chunk_tokens = self._count_tokens(chunk_text)

            # Check if adding this chunk would exceed budget
            overhead = sep_tokens if context_parts else 0
            if used_tokens + chunk_tokens + overhead > self.max_tokens:
                # If we haven't included anything yet, include at least the first (truncated)
                if not included:
                    truncated = self._truncate_to_tokens(
                        chunk_text, self.max_tokens
                    )
                    context_parts.append(truncated)
                    included.append(result)
                break

            context_parts.append(chunk_text)
            included.append(result)
            used_tokens += chunk_tokens + overhead

        context = separator.join(context_parts)
        return context, included

    def _format_chunk(
        self, index: int, result: SearchResult, include_metadata: bool
    ) -> str:
        """Format a single chunk for the context window."""
        parts = [f"[{index}] {result.content}"]

        if include_metadata:
            source = f"Source: {result.document_name}"
            if result.chunk_order > 0:
                source += f" (section {result.chunk_order})"
            parts.append(source)

        return "\n".join(parts)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit."""
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoder.decode(tokens[:max_tokens]) + "..."

    def build_prompt_context(
        self,
        results: list[SearchResult],
        query: str,
        system_note: str = "Use ONLY the provided context to answer. Cite sources using [n] notation.",
    ) -> dict:
        """Build a complete prompt context dict ready for LLM.

        Returns dict with:
        - context: assembled context string
        - sources: list of included results
        - token_usage: token counts
        - prompt_parts: system, context, query sections
        """
        context, included = self.build(results)
        context_tokens = self._count_tokens(context)
        query_tokens = self._count_tokens(query)
        system_tokens = self._count_tokens(system_note)

        return {
            "context": context,
            "sources": [
                {
                    "index": i + 1,
                    "document": r.document_name,
                    "document_id": r.document_id,
                    "chunk_id": r.chunk_id,
                    "score": r.final_score,
                }
                for i, r in enumerate(included)
            ],
            "token_usage": {
                "context_tokens": context_tokens,
                "query_tokens": query_tokens,
                "system_tokens": system_tokens,
                "total": context_tokens + query_tokens + system_tokens,
                "budget": self.max_tokens,
                "remaining": self.max_tokens - context_tokens,
            },
            "prompt_parts": {
                "system": system_note,
                "context": context,
                "query": query,
            },
        }
