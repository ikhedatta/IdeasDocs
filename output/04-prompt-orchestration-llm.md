# 4. Prompt Orchestration & LLM Usage

## 4.1 How Prompts Are Structured

RAGFlow uses a **layered prompt architecture** with Jinja2 templates, XML-tagged sections, and programmatic assembly.

### System Prompt Structure (Chat Mode)

```
[User-defined system prompt]
  └── Can contain XML-tagged sections:
      <CITATION_GUIDELINES>...</CITATION_GUIDELINES>
      <TASK_ANALYSIS>...</TASK_ANALYSIS>
      <CONTEXT_SUMMARY>...</CONTEXT_SUMMARY>

[Citation rules] (appended when chunks are retrieved)
  └── Loaded from rag/prompts/citation_prompt.md
  └── Includes: format rules, must-cite matrix, examples

[Knowledge base context] (formatted by kb_prompt())
  └── Structured chunks with ID, Title, URL, Metadata, Content
  └── Token-aware: truncates at 97% of context window
```

### Prompt Template Files

**Location**: `rag/prompts/`

| Template | Purpose | Key Variables |
|----------|---------|---------------|
| `citation_prompt.md` | Citation enforcement rules | None (static) |
| `citation_plus_prompt.md` | Enhanced citation with sources | `{sources}` |
| `ask_summary.md` | Context-aware summarization | `{cluster_content}` |
| `structured_output_prompt.md` | Force JSON output | `{schema}` |
| `vision_llm_describe_prompt.md` | Page-level image description | `{context}` |
| `analyze_task_system.md` | Agent task decomposition | `{tools}`, `{settings}` |

### Template Rendering

```python
# rag/prompts/__init__.py
PROMPT_JINJA_ENV = jinja2.Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)

def load_prompt(name: str) -> str:
    path = os.path.join(PROMPT_DIR, f"{name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

# Usage:
template = PROMPT_JINJA_ENV.from_string(load_prompt("citation_prompt"))
rendered = template.render(variable=value)
```

---

## 4.2 Context Injection Strategy

### Knowledge Base Context Format

```
ID: 1
├── Title: Safety_Guidelines_v3.pdf
├── URL: https://docs.company.com/safety
├── Department: Compliance
├── Last Updated: 2024-03-15
└── Content:
All personnel must complete safety training within 30 days of hire.
The training includes fire evacuation procedures, chemical handling,
and personal protective equipment (PPE) requirements.
------
ID: 2
├── Title: HR_Onboarding_Policy.docx
├── URL: https://docs.company.com/hr/onboarding
└── Content:
New employees are assigned a buddy mentor for the first 90 days...
```

**Key Design Decisions**:
1. **Hierarchical format**: Tree-like structure makes it easy for LLMs to parse
2. **Metadata inclusion**: Title, URL, custom fields provide context beyond raw text
3. **Separator**: `------` between chunks prevents blending
4. **Token budget**: 97% of context window allocated to knowledge, 3% reserved

### Multi-Turn History Management

```python
# Token-aware message fitting (rag/llm/chat_model.py)
def message_fit_in(msg, max_length=4000):
    """Fit conversation history within token budget."""
    total = sum(num_tokens_from_string(m["content"]) for m in msg)
    
    if total > max_length:
        # Strategy: keep system + latest user message
        # Truncate middle history
        msg_ = [m for m in msg if m["role"] == "system"]
        msg_.append(msg[-1])  # Keep latest query
        # Truncate content to fit
```

---

## 4.3 Guardrails & Hallucination Prevention

### Citation-Based Grounding

The primary anti-hallucination mechanism is **citation enforcement**:

```markdown
# From citation_prompt.md

## Core Rules:
1. ONLY use information from the <context></context> section
2. Every factual claim MUST have a citation in [ID:X] format
3. If information isn't in context, explicitly say so
4. DO NOT make things up, especially numbers

## Must-Cite Matrix:
| Must Cite                         | Must NOT Cite              |
|-----------------------------------|----------------------------|
| Quantitative data (numbers, %)    | Common knowledge           |
| Temporal claims (dates)           | Transitional phrases       |
| Causal relationships ("because")  | General introductions      |
| Technical definitions             | Personal analysis          |
| Comparative statements            |                            |
```

### Empty Context Handling

```python
# Dialog config includes empty_response
if not retrieved_chunks:
    return dialog.prompt_config.get("empty_response", 
        "Sorry, I don't find relevant content to answer your question.")
```

When no relevant chunks are found, the system returns a configured "I don't know" response instead of letting the LLM hallucinate from parametric knowledge.

### Post-Generation Citation Validation

```python
# After LLM generates response:
# 1. Extract all [ID:X] citations
# 2. Map to actual chunk IDs
# 3. If LLM didn't cite, auto-cite via vector similarity
# 4. Repair malformed citations
# 5. Aggregate referenced documents for response metadata
```

### Structured Output Enforcement

For agent components that need structured output:

```python
# Force JSON conformance
async def _force_format_to_schema_async(self, text, schema_prompt):
    """If LLM output doesn't match schema, retry with explicit format instruction."""
    fmt_msgs = [
        {"role": "system", "content": schema_prompt + "\nIMPORTANT: Output ONLY valid JSON."},
        {"role": "user", "content": text},
    ]
    result = await self._generate_async(fmt_msgs)
    return json_repair.loads(result)  # json_repair handles common LLM JSON mistakes
```

---

## 4.4 LLM Abstraction Architecture

### Factory Pattern

```python
# rag/llm/__init__.py
ChatModel = {}      # factory_name → ChatModelClass
EmbeddingModel = {} # factory_name → EmbeddingModelClass
RerankModel = {}    # factory_name → RerankModelClass
Seq2txtModel = {}   # factory_name → ASRModelClass
CvModel = {}        # factory_name → Image2TextModelClass
TTSModel = {}       # factory_name → TTSModelClass

# Auto-registration via _FACTORY_NAME attribute
for module_name, mapping_dict in MODULE_MAPPING.items():
    module = importlib.import_module(f"rag.llm.{module_name}")
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if hasattr(obj, "_FACTORY_NAME"):
            factory_names = obj._FACTORY_NAME if isinstance(obj._FACTORY_NAME, list) else [obj._FACTORY_NAME]
            for fn in factory_names:
                mapping_dict[fn] = obj
```

### Usage in Services

```python
# api/db/services/dialog_service.py
def load_models(dialog, tenant):
    chat_mdl = ChatModel[tenant_llm.llm_factory](
        api_key=tenant_llm.api_key,
        model_name=tenant_llm.llm_name,
        base_url=tenant_llm.api_base,
    )
    embd_mdl = EmbeddingModel[kb.embd_id.split("/")[0]](...)
    rerank_mdl = RerankModel[dialog.rerank_id.split("/")[0]](...) if dialog.rerank_id else None
```

### Error Handling & Retry

```python
# Classified error codes
class LLMErrorCode(StrEnum):
    ERROR_RATE_LIMIT = "RATE_LIMIT_EXCEEDED"
    ERROR_AUTHENTICATION = "AUTH_ERROR"
    ERROR_QUOTA = "QUOTA_EXCEEDED"
    ERROR_TIMEOUT = "TIMEOUT"
    ERROR_MAX_RETRIES = "MAX_RETRIES_EXCEEDED"
    # ...

# Exponential backoff with jitter
delay = base_delay * random.uniform(10, 150)  # 20-300s range
```

### Model Family Policy Enforcement

RAGFlow handles model-specific quirks:
```python
def _apply_model_family_policies(self):
    if "qwen3" in self.model_name:
        self.extra_body["enable_thinking"] = False
    if "gpt-5" in self.model_name:
        # Remove unsupported params
        del gen_conf["frequency_penalty"]
    if "kimi-k2" in self.model_name:
        self.extra_body["thinking"] = {"type": "enabled"}
```

---

## 4.5 What to Adopt for Our System

### Prompt Architecture

```python
# Recommended prompt structure for controlled RAG

SYSTEM_PROMPT_TEMPLATE = """
You are a helpful assistant that answers questions based ONLY on the provided context.

## Rules:
1. Only use information from the <context> section below
2. Cite sources using [Source:ID] format after every factual claim
3. If the context doesn't contain relevant information, say:
   "I don't have enough information in my approved sources to answer this."
4. Never generate information beyond what's in the context
5. For numerical data, always cite the exact source

## Citation Format:
- Place [Source:ID] BEFORE the period
- Maximum 3 citations per sentence
- Example: "Revenue grew 15% year-over-year [Source:3]."

<context>
{formatted_chunks}
</context>
"""

USER_PROMPT_TEMPLATE = """
Question: {query}

Remember: Only use information from the provided context. Cite every factual claim.
"""
```

### Context Formatting

```python
def format_context(chunks: list[RetrievedChunk], max_tokens: int = 8000) -> str:
    """Format retrieved chunks for LLM context injection."""
    formatted = []
    token_count = 0
    
    for i, chunk in enumerate(chunks, 1):
        entry = f"[Source {i}]\n"
        entry += f"Document: {chunk.document_title}\n"
        if chunk.metadata:
            for k, v in chunk.metadata.items():
                entry += f"{k}: {v}\n"
        entry += f"Content:\n{chunk.text}\n"
        entry += "---\n"
        
        entry_tokens = count_tokens(entry)
        if token_count + entry_tokens > max_tokens * 0.95:
            break
        
        formatted.append(entry)
        token_count += entry_tokens
    
    return "\n".join(formatted)
```

### Citation Extraction

```python
import re

def extract_citations(response: str) -> list[int]:
    """Extract source IDs from LLM response."""
    pattern = r'\[Source:(\d+)\]'
    return list(set(int(m) for m in re.findall(pattern, response)))

def build_references(citations: list[int], chunks: list[RetrievedChunk]) -> list[dict]:
    """Map citation IDs to source documents."""
    return [
        {
            "source_id": cid,
            "document_title": chunks[cid - 1].document_title,
            "document_id": chunks[cid - 1].document_id,
            "chunk_text": chunks[cid - 1].text[:200],
            "relevance_score": chunks[cid - 1].score,
        }
        for cid in citations
        if 0 < cid <= len(chunks)
    ]
```

### Hallucination Safeguards

1. **Empty context handling**: Return configured "I don't know" response
2. **Citation enforcement**: Prompt rules + post-processing validation
3. **Temperature control**: Use 0.0-0.3 for factual Q&A (RAGFlow defaults to 0.1)
4. **Max tokens limit**: Prevent rambling responses
5. **Structured output**: Force JSON when needed (with `json_repair` fallback)
