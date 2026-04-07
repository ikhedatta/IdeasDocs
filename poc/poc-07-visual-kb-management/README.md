# POC-07: Visual Knowledge Base Management UI

## Feature
**Chunk-level visibility, inspection, toggle, editing, and KB dashboard — in the browser**

This is the frontend counterpart to POC-04 (Chunk Management API) and POC-06 (KB Manager). It gives knowledge base administrators a visual interface to inspect every chunk, see processing status, toggle chunks on/off, and edit content inline.

## What Problem It Solves
- **Invisible indexing**: Without a UI, admins can't see what the system actually indexed
- **Chunk quality is unknowable**: You need to _see_ chunks to know if parsing worked
- **Toggle without code**: Enable/disable chunks with a click, not a curl command
- **Inline editing**: Fix OCR errors or bad parses directly in the browser
- **Processing oversight**: See which documents succeeded, failed, or are still processing

## Key RAGFlow Patterns Implemented
- **KB Dashboard** — grid of knowledge bases with doc count, chunk count, status
- **Document list with status badges** — queued/parsing/chunking/ready/error
- **Chunk explorer** — paginated list with content preview, scores, active toggle
- **Inline chunk editor** — edit content, auto-re-embed on save
- **Chunk detail panel** — full content, metadata, token count, vector preview

## Architecture

```
Next.js 14 (App Router)
    │
    ├── /                       → KB Dashboard (grid of knowledge bases)
    ├── /kb/[id]                → KB detail: documents + stats
    ├── /kb/[id]/documents/[docId] → Chunk explorer for a document
    └── /kb/[id]/chunks         → All chunks in KB (search/filter)
    │
    ▼
FastAPI Backend (POC-04 + POC-06)
    ├── GET  /kb                → List KBs
    ├── GET  /kb/{id}/stats     → KB statistics
    ├── GET  /kb/{id}/documents → Document list
    ├── GET  /chunks?kb_id=...  → Chunk list with filters
    ├── PATCH /chunks/{id}/toggle → Toggle active/inactive
    ├── PUT  /chunks/{id}       → Edit chunk (triggers re-embed)
    └── POST /chunks            → Manual chunk creation
```

## Screenshots (conceptual)

```
┌─────────────────────────────────────────────────────────────┐
│  📚 Knowledge Bases                            [+ Create]   │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│ │ HR Policies  │  │ Tech Docs    │  │ Legal        │       │
│ │ 24 docs      │  │ 156 docs     │  │ 42 docs      │       │
│ │ 1,240 chunks │  │ 8,432 chunks │  │ 3,100 chunks │       │
│ │ ● Ready      │  │ ◐ 2 parsing  │  │ ● Ready      │       │
│ └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  📄 HR Policies → employee_handbook.pdf (156 chunks)        │
├─────────────────────────────────────────────────────────────┤
│ [🔍 Search chunks...] [Status: ▾ All] [Sort: ▾ Order]      │
│                                                             │
│ ┌─ Chunk #1 ──────────────────── ✅ Active ── [Toggle] ──┐ │
│ │ "Section 1.1 - Employee Benefits                       │ │
│ │  All full-time employees are eligible for health..."    │ │
│ │ 📊 128 tokens │ Score: 0.89 │ 📝 Edit                  │ │
│ └────────────────────────────────────────────────────────┘ │
│ ┌─ Chunk #2 ──────────────────── ❌ Disabled ─ [Toggle] ─┐ │
│ │ "Table 2.1 - PTO Accrual Rates..."                     │ │
│ │ 📊 256 tokens │ Score: 0.72 │ 📝 Edit                  │ │
│ └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 14.x | React framework with App Router, Server Components |
| React | 18.x | UI library |
| Tailwind CSS | 3.x | Utility-first styling |
| Zustand | 4.x | Lightweight state management |
| Lucide React | latest | Icon library |

## File Structure

```
poc-07-visual-kb-management/
├── README.md
├── package.json
├── next.config.js
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── .env.local.example
├── src/
│   ├── app/
│   │   ├── layout.tsx         — Root layout with sidebar nav
│   │   ├── page.tsx           — KB Dashboard (home)
│   │   ├── globals.css        — Tailwind imports + custom styles
│   │   └── kb/
│   │       └── [kbId]/
│   │           ├── page.tsx   — KB detail: docs + stats
│   │           └── chunks/
│   │               └── page.tsx — Chunk explorer with filters
│   ├── components/
│   │   ├── KBCard.tsx         — Knowledge base card for dashboard
│   │   ├── DocumentList.tsx   — Document list with status badges
│   │   ├── ChunkCard.tsx      — Single chunk display with toggle
│   │   ├── ChunkEditor.tsx    — Inline chunk editing modal
│   │   ├── ChunkDetail.tsx    — Full chunk detail panel
│   │   ├── StatsBar.tsx       — KB statistics bar
│   │   ├── SearchFilter.tsx   — Search + filter controls
│   │   └── StatusBadge.tsx    — Document/chunk status indicator
│   ├── lib/
│   │   ├── api.ts             — API client for backend calls
│   │   └── types.ts           — TypeScript interfaces
│   └── store/
│       └── useKBStore.ts      — Zustand store for KB state
```

## How to Run

```bash
cd poc-07-visual-kb-management
npm install
cp .env.local.example .env.local   # Set API URL
npm run dev                         # → http://localhost:3000

# Backend must be running:
# POC-04 on :8004 (chunk management)
# POC-06 on :8006 (KB management)
```

## How to Extend

1. **Drag-and-drop upload**: Add file upload zone on KB detail page
2. **Chunk diff view**: Show before/after when editing chunks
3. **Bulk select**: Checkbox multi-select for batch toggle/delete
4. **Real-time updates**: WebSocket for processing status updates
5. **Vector visualization**: t-SNE/UMAP 2D plot of chunk embeddings
