# POC-08: Retrieval Debugging & Transparency UI

## Feature
**Interactive retrieval testing, score decomposition visualization, and A/B config comparison — in the browser**

This is the frontend for POC-05 (Retrieval Debugger API). It lets developers and admins visually test retrieval quality, see per-chunk score breakdowns, compare two configurations side-by-side, and run batch test suites.

## What Problem It Solves
- **Black-box retrieval**: Without visual score breakdown, you can't understand _why_ results rank the way they do
- **Tuning by guesswork**: No tool to interactively change weights and see results immediately
- **No regression visibility**: After config changes, no way to quickly verify quality
- **Score opacity**: Dense vs. sparse vs. rerank contributions are invisible without a debugger

## Key RAGFlow Patterns Implemented
- **Retrieval test** — run a query and see ranked results with per-step scores
- **Score bars** — visual breakdown: dense (blue), sparse (orange), rerank (purple), final (green)
- **A/B comparison** — split view: same query, two configs, with overlap analysis
- **Timing breakdown** — per-step latency: embed, search, rerank
- **Batch test runner** — upload test suite, see Recall@K metrics

## Architecture

```
Next.js 14 (App Router)
    │
    ├── /                          → Debug search (single query)
    ├── /compare                   → A/B config comparison
    └── /batch                     → Batch test suite runner
    │
    ▼
FastAPI Backend (POC-05)
    ├── POST /debug/search         → Debug search with scores
    ├── POST /debug/compare        → Side-by-side comparison
    └── POST /debug/batch          → Batch test with Recall@K
```

## Screenshots (conceptual)

```
┌──────────────────────────────────────────────────────────────┐
│  🔍 Retrieval Debugger                                       │
│  ┌────────────────────────────────────────────────── [Search]│
│  │ What is the fire safety evacuation procedure?             │
│  └───────────────────────────────────────────────────────────│
│  KB: [HR Policies ▾]  Top K: [20]  Dense: [0.7]  Sparse:[0.3]│
│  Rerank: [rerank-english-v3.0 ▾]                             │
├──────────────────────────────────────────────────────────────┤
│  📊 5 results (23ms embed, 45ms search, 120ms rerank)        │
│                                                              │
│  #1 ████████████████████░░░░ 0.92  fire_safety.pdf §3        │
│     Dense: 0.87 ████████░  Sparse: 0.34 ███░  Rerank: 0.92  │
│     "All employees must evacuate via the nearest..."         │
│                                                              │
│  #2 ██████████████████░░░░░░ 0.85  fire_safety.pdf §7        │
│     Dense: 0.81 ███████░░  Sparse: 0.45 ████░ Rerank: 0.85  │
│     "Fire wardens are responsible for ensuring..."           │
│                                                              │
│  #3 ████████████████░░░░░░░░ 0.71  emergency_proc.pdf §2     │
│     Dense: 0.69 ██████░░░  Sparse: 0.28 ██░░░ Rerank: 0.71  │
│     "Emergency procedures include fire, earthquake..."       │
└──────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 14.x | React framework with App Router |
| React | 18.x | UI library |
| Tailwind CSS | 3.x | Styling |
| Zustand | 4.x | State management |
| Lucide React | latest | Icons |

## File Structure

```
poc-08-retrieval-debugger-ui/
├── README.md
├── package.json
├── next.config.js
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── .env.local.example
├── src/
│   ├── app/
│   │   ├── layout.tsx           — Root layout with tab nav
│   │   ├── page.tsx             — Debug search page
│   │   ├── globals.css
│   │   ├── compare/
│   │   │   └── page.tsx         — A/B comparison page
│   │   └── batch/
│   │       └── page.tsx         — Batch test suite page
│   ├── components/
│   │   ├── QueryInput.tsx       — Search input + config controls
│   │   ├── ConfigPanel.tsx      — Retrieval config sliders
│   │   ├── ResultCard.tsx       — Single result with score bars
│   │   ├── ScoreBar.tsx         — Visual score breakdown bar
│   │   ├── TimingBar.tsx        — Latency timing visualization
│   │   ├── CompareView.tsx      — Split A/B comparison view
│   │   ├── OverlapBadge.tsx     — Jaccard similarity badge
│   │   └── BatchResults.tsx     — Test suite results table
│   ├── lib/
│   │   ├── api.ts               — API client for debug endpoints
│   │   └── types.ts             — TypeScript interfaces
│   └── store/
│       └── useDebugStore.ts     — Zustand store
```

## How to Run

```bash
cd poc-08-retrieval-debugger-ui
npm install
cp .env.local.example .env.local   # Set API URL
npm run dev                         # → http://localhost:3001

# Backend must be running: POC-05 on :8005
```

## How to Extend

1. **Config presets**: Save/load retrieval config profiles
2. **Query history**: Track past queries and compare results over time
3. **Export results**: Download debug data as JSON/CSV
4. **Live config sliders**: Real-time updates as you drag weight sliders
5. **Chunk highlighting**: Click a result to see its position in the original document
