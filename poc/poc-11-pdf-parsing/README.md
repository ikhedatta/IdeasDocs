# POC-11 — Efficient PDF Parsing Pipeline

## ══════════════════════════════════════════════════════════════════════
## PART 1: Architecture Overview
## ══════════════════════════════════════════════════════════════════════

### Problem Statement

Canva-generated resume PDFs (and similar design-tool PDFs) embed custom
subset fonts that break standard text extraction. Words like "Infosys",
"Magna", and other proper nouns appear as garbled punctuation or are
silently dropped because the font's internal CID→Unicode mapping is
incomplete or deliberately obfuscated.

### Root Cause Analysis

| Symptom | Root Cause | Detection Method |
|---------|-----------|------------------|
| Missing words ("Infosys") | Subset font maps glyph IDs to PUA codepoints (U+E000–U+F8FF) | Scan character unicode ranges |
| Random punctuation output | Font CMap maps CJK glyphs to ASCII punct codepoints | Subset-font ratio + punct ratio heuristic |
| `(cid:123)` placeholders | pdfminer cannot resolve CID to unicode at all | Regex `r"\(cid\s*:\s*\d+\s*\)"` |
| Empty text from pdfplumber | Font has no ToUnicode CMap entry | Character count == 0 for visible region |

### Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PDF INPUT                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  CLASSIFIER  │   Detect: text-based vs scanned
                    │  (Phase 0)   │   vs mixed vs design-tool (Canva)
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
    │  TEXT-ONLY │   │   HYBRID  │   │  OCR-ONLY  │
    │  (fast)    │   │ text+OCR  │   │  (Canva/   │
    │            │   │ per-box   │   │  scanned)  │
    └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
          │                │                │
          └────────────────┼────────────────┘
                           │
                    ┌──────▼──────┐
                    │   LAYOUT    │   Detect regions: title, text,
                    │  ANALYSIS   │   table, header, footer, figure
                    │  (Phase 2)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   READING   │   Column detection, merge boxes,
                    │   ORDER     │   reconstruct natural flow
                    │  (Phase 3)  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  CHUNKING   │   Semantic + token-bounded chunks
                    │  (Phase 4)  │   with overlap & metadata
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  EMBEDDING  │   Interface-only in POC;
                    │   HOOK      │   plug any model
                    │  (Phase 5)  │
                    └─────────────┘
```

### Module Structure

```
poc-11-pdf-parsing/
├── README.md                  ← This file
├── requirements.txt           ← Dependencies
├── config.py                  ← Configuration constants
├── models.py                  ← Data models (Pydantic)
├── classifier.py              ← PDF type classifier (Phase 0)
├── text_extractor.py          ← Text extraction + garble detection (Phase 1)
├── ocr_engine.py              ← OCR fallback engine (Phase 1b)
├── layout_analyzer.py         ← Layout region detection (Phase 2)
├── reading_order.py           ← Column detection + merge (Phase 3)
├── chunker.py                 ← Semantic + token chunking (Phase 4)
├── embeddings.py              ← Embedding interface hook (Phase 5)
├── pipeline.py                ← End-to-end orchestrator
├── main.py                    ← FastAPI entry point
└── tests/
    └── test_pipeline.py       ← Unit + integration tests
```


## ══════════════════════════════════════════════════════════════════════
## PART 2: RAGFlow-Inspired Design Insights
## ══════════════════════════════════════════════════════════════════════

### How RAGFlow Achieves High-Quality PDF Parsing

RAGFlow's `RAGFlowPdfParser` (2000+ lines in `deepdoc/parser/pdf_parser.py`)
is the gold standard this POC draws from. Key techniques:

#### 1. Three-Strategy Garble Detection

RAGFlow doesn't just try to extract text — it **validates** every text
box against three independent garble detectors:

| Strategy | What It Catches | How |
|----------|----------------|-----|
| **PUA Detection** | Private Use Area characters (U+E000–F8FF) | Check `ord(ch)` ranges per character |
| **CID Pattern** | Unmapped glyphs from pdfminer | Regex `(cid:\d+)` in text |
| **Font-Encoding** | Canva-style subset fonts | >30% chars from subset fonts AND <5% CJK AND >40% ASCII punct |

When *any* strategy triggers → text is cleared → OCR fills the gap.

#### 2. Hybrid Per-Box Text+OCR

RAGFlow does NOT choose "text mode" or "OCR mode" for the whole document.
Instead, it extracts text per bounding box from pdfplumber AND runs OCR
on the page image, then **per box**:
- If pdfplumber text is clean → use it (faster, more accurate for good PDFs)
- If pdfplumber text is garbled → crop the box region from page image → OCR

This is critical for Canva PDFs where *some* text blocks extract fine
(e.g., bullet characters, numbers) but others are garbled (proper nouns
in custom fonts).

#### 3. XGBoost-Based Text Merging

Instead of rule-based paragraph detection, RAGFlow uses an XGBoost model
with 31 features (layout type, y-distance, x-alignment, font size, text
patterns) to predict whether adjacent boxes should merge. This handles
irregular layouts from design tools better than heuristic-only approaches.

#### 4. Multi-Column Detection via K-Means

Canva resumes are typically 2-column. RAGFlow uses K-Means clustering on
box x-positions with silhouette score to auto-detect column count, then
sorts reading order column-by-column.

#### 5. Position Preservation for Retrieval

Every chunk carries `position_int` = `[[page, x0, x1, top, bottom], ...]`
so the UI can highlight the exact PDF region a chunk came from. This POC
preserves the same metadata.

### What This POC Adapts vs. Simplifies

| RAGFlow Component | This POC | Rationale |
|-------------------|----------|-----------|
| YOLO layout model (ONNX) | Heuristic + optional model hook | Avoids 200MB model download for POC |
| PaddleOCR (detect+recognize) | Tesseract + optional PaddleOCR hook | Tesseract is pip-installable, no GPU needed |
| XGBoost text merger (31 features) | Rule-based merger (12 heuristics) | Good enough for resume layouts; pluggable |
| pdfplumber + custom C extension | pdfplumber + PyMuPDF (fitz) | PyMuPDF handles more edge cases for CID fonts |
| Async GPU dispatch | `concurrent.futures` thread pool | POC runs on CPU; production swaps in GPU pool |


## ══════════════════════════════════════════════════════════════════════
## PART 4: Performance Considerations
## ══════════════════════════════════════════════════════════════════════

### Bottleneck Analysis

| Stage | Time (typical 2-page resume) | Bottleneck | Memory |
|-------|------------------------------|-----------|---------|
| PDF load + page render | ~200ms | I/O + image alloc | ~50MB for 300 DPI images |
| Text extraction (pdfplumber) | ~100ms | CPU (font parsing) | ~10MB |
| Garble detection | ~5ms | CPU (string scan) | Negligible |
| OCR (Tesseract, per page) | ~2-5s | CPU (most expensive) | ~200MB model |
| OCR (PaddleOCR, GPU) | ~200-500ms | GPU mem | ~500MB VRAM |
| Layout analysis (heuristic) | ~10ms | CPU | Negligible |
| Layout analysis (YOLO) | ~100ms | GPU inference | ~200MB VRAM |
| Chunking | ~5ms | CPU | Negligible |
| Embedding (per chunk) | ~50-200ms | GPU/API | Varies |

**Total for clean PDF**: ~300ms (skip OCR)
**Total for Canva PDF**: ~3-8s (OCR fallback per garbled box)

### Optimization Strategies

1. **Classify-First**: Detect PDF type before any heavy processing.
   Clean text PDFs skip OCR entirely → 10x faster.

2. **Box-Level OCR**: Only OCR the garbled boxes, not the full page.
   Canva resumes typically have 30-60% clean boxes → 2-3x OCR savings.

3. **Page-Level Parallelism**: Process pages concurrently via thread pool.
   2-page resume → 2 threads → near-linear speedup for OCR.

4. **Image Caching**: Cache rendered page images (they're reused for OCR
   of multiple boxes on the same page).

5. **Streaming Chunks**: Yield chunks as they're produced instead of
   accumulating all in memory → constant memory for large documents.

6. **OCR Result Cache**: Hash (page_image + box_coords) → cache OCR text.
   Repeated processing of same PDF skips OCR entirely.


## ══════════════════════════════════════════════════════════════════════
## PART 5: Production Handoff Guide
## ══════════════════════════════════════════════════════════════════════

### For the Next LLM / Engineer

This POC is designed to be **extended**, not rewritten. Every module has
clear interfaces and the pipeline is pluggable at each phase.

### What Works Now (POC-Complete)

- [x] PDF type classification (text vs scanned vs Canva)
- [x] Three-strategy garble detection (PUA, CID, font-encoding)
- [x] Hybrid per-box text + OCR fallback
- [x] PyMuPDF + pdfplumber dual extraction
- [x] Tesseract OCR integration
- [x] Heuristic layout analysis (title, header, table, text regions)
- [x] Multi-column reading order detection
- [x] Semantic + token-bounded chunking with overlap
- [x] Position metadata preservation per chunk
- [x] Embedding interface (abstract base class)
- [x] FastAPI endpoint for upload → parse → chunks
- [x] Comprehensive unit tests

### What Needs Production Hardening

#### Priority 1 — Must Have

| Component | Current State | Production Target |
|-----------|--------------|-------------------|
| **OCR Engine** | Tesseract (CPU, slow) | PaddleOCR with GPU (5-10x faster) |
| **Layout Model** | Heuristic rules | YOLO/LayoutLM ONNX model (RAGFlow uses this) |
| **Text Merger** | 12-rule heuristic | XGBoost model trained on document pairs |
| **Error Handling** | Basic try/except | Structured errors with retry + dead-letter queue |
| **Monitoring** | Print/logging | OpenTelemetry traces + Prometheus metrics |
| **File Validation** | Basic size check | Malware scan, PDF/A conformance, page limit |

#### Priority 2 — Should Have

| Component | What to Add |
|-----------|------------|
| **Task Queue** | Celery/Redis or cloud equivalent (SQS) for async processing |
| **Storage** | MinIO/S3 for PDFs + images; PostgreSQL for metadata |
| **Caching** | Redis cache for OCR results keyed by content hash |
| **Rate Limiting** | Per-user upload limits, concurrent parse limits |
| **Table Extraction** | Dedicated table structure recognition (camelot, TSR model) |
| **Multi-Language** | Language detection → appropriate OCR model/tokenizer |

#### Priority 3 — Nice to Have

| Component | What to Add |
|-----------|------------|
| **Vision LLM Fallback** | GPT-4V / Qwen-VL for extremely complex layouts |
| **Font Repair** | Attempt ToUnicode CMap reconstruction before OCR |
| **Incremental Parsing** | Parse only changed pages when PDF is updated |
| **Batch API** | Accept ZIP of PDFs, process in parallel, webhook on completion |

### Architecture Upgrade Path

```
Current (POC):
  HTTP Upload → FastAPI → sync parse → return chunks

Production Target:
  HTTP Upload → API Gateway → Message Queue (Redis/SQS)
       ↓                           ↓
  Store PDF in S3            Worker Pool (K8s pods)
       ↓                           ↓
  Return task_id             Parse → Chunk → Embed → Index
       ↓                           ↓
  Poll /tasks/{id}           Store in Elasticsearch/Qdrant
                                    ↓
                             Webhook notification
```

### TODO Roadmap (Ordered)

```
1. [ ] Replace Tesseract with PaddleOCR (GPU-accelerated)
2. [ ] Add YOLO layout detection model (ONNX runtime)
3. [ ] Train XGBoost text-merge model on document corpus
4. [ ] Add Celery task queue for async processing
5. [ ] Add MinIO storage for PDF + extracted images
6. [ ] Add Redis caching layer for OCR results
7. [ ] Add OpenTelemetry instrumentation
8. [ ] Add table structure recognition (bordered + borderless)
9. [ ] Add multi-language OCR model selection
10. [ ] Load test: 100 concurrent PDFs, measure P95 latency
11. [ ] Add Vision LLM fallback for P0 parse failures
12. [ ] Kubernetes deployment manifests + HPA autoscaling
```

### Key Interfaces for Extension

Every phase implements an abstract base class. To swap implementations:

```python
# Example: Replace Tesseract with PaddleOCR
class PaddleOCREngine(BaseOCREngine):
    async def recognize_region(self, image, bbox) -> str: ...
    async def recognize_page(self, image) -> list[OCRBox]: ...

# Example: Replace heuristic layout with YOLO
class YOLOLayoutAnalyzer(BaseLayoutAnalyzer):
    def analyze(self, page_image, text_boxes) -> list[LayoutRegion]: ...

# Example: Add OpenAI embeddings
class OpenAIEmbedder(BaseEmbedder):
    async def embed_chunks(self, chunks) -> list[list[float]]: ...
```

### Critical Configuration for Canva PDFs

```python
# These thresholds are tuned for Canva resume PDFs specifically:
GARBLE_PUA_THRESHOLD = 0.3      # 30% PUA chars → garbled
GARBLE_SUBSET_FONT_RATIO = 0.3  # 30% chars from subset fonts
GARBLE_CJK_RATIO = 0.05         # <5% CJK output
GARBLE_PUNCT_RATIO = 0.4        # >40% ASCII punct → font-encoding garble
OCR_CONFIDENCE_THRESHOLD = 0.5  # Minimum OCR confidence to accept
```

These values come directly from RAGFlow's battle-tested defaults.
