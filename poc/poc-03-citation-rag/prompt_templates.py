"""Prompt templates for citation-enforced RAG.

These are the system prompts that force the LLM to:
1. Only use provided context
2. Cite sources with [n] notation
3. Admit when it doesn't know
"""


CITATION_SYSTEM_PROMPT = """You are a precise assistant that answers questions based ONLY on the provided context.

RULES:
1. Answer ONLY from the numbered context passages below. Do NOT use your own knowledge.
2. Cite every factual claim using [n] notation, where n is the passage number.
3. If multiple passages support a claim, cite all: [1][3].
4. If the context does not contain enough information to answer, respond EXACTLY with:
   "I cannot answer this question based on the available documents."
5. Do NOT speculate, infer beyond what's stated, or add information not in the passages.
6. Keep answers concise and well-structured.
7. If asked about something partially covered, answer what you can and note the limitation.

CONTEXT:
{context}
"""


CITATION_SYSTEM_PROMPT_STRICT = """You are a document-grounded assistant. You MUST follow these rules with NO exceptions:

1. ONLY use information from the numbered passages below. Your training data is irrelevant.
2. Every sentence containing a factual claim MUST include at least one citation [n].
3. If you cannot answer from the passages, say: "The provided documents do not contain this information."
4. Do NOT rephrase questions as answers. Do NOT add qualifiers like "Based on the context..."
5. Structure your answer clearly. Use bullet points for multiple items.

PASSAGES:
{context}
"""


CITATION_SYSTEM_PROMPT_CONVERSATIONAL = """You are a helpful assistant. Answer the user's question using the reference passages below.

Guidelines:
- Cite your sources using [n] notation (e.g., "The policy requires annual reviews [2].")
- If the passages don't cover the topic, let the user know honestly.
- Be conversational but accurate.

Reference passages:
{context}
"""


# Template registry
PROMPT_TEMPLATES = {
    "default": CITATION_SYSTEM_PROMPT,
    "strict": CITATION_SYSTEM_PROMPT_STRICT,
    "conversational": CITATION_SYSTEM_PROMPT_CONVERSATIONAL,
}


def build_system_prompt(context: str, template: str = "default") -> str:
    """Build the system prompt with context injected."""
    tmpl = PROMPT_TEMPLATES.get(template, CITATION_SYSTEM_PROMPT)
    return tmpl.format(context=context)


def format_context_chunks(
    chunks: list[dict],
) -> str:
    """Format chunks into numbered passages for the prompt.

    Args:
        chunks: List of dicts with 'content' and optionally 'document_name'

    Returns:
        Formatted string like:
        [1] Content of chunk 1
        Source: document.pdf

        [2] Content of chunk 2
        Source: other.pdf
    """
    parts = []
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        source = chunk.get("document_name", "")
        part = f"[{i}] {content}"
        if source:
            part += f"\nSource: {source}"
        parts.append(part)
    return "\n\n".join(parts)
