# POC-10 · Data Source Management UI

> **Next.js 14 / React 18 / Tailwind CSS** frontend for managing external data source connectors, browsing content, and monitoring sync activity.

## Screens

| Page | Path | Description |
|------|------|-------------|
| **Dashboard** | `/` | Overview stats, list of connected sources |
| **Source Catalog** | `/catalog` | Browse 13 available sources, filter by category |
| **My Connections** | `/connections` | Table of all connector instances |
| **Connection Detail** | `/connections/[id]` | Config, sync logs, content browser tabs |
| **Connect Wizard** | `/connect/[source]` | 3-step wizard: credentials → config → confirm |

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Next.js App  (:3002)                           │
│                                                 │
│  Dashboard → Catalog → Connect Wizard           │
│  Connections → Connection Detail                 │
│    ├── Overview (config + credentials)           │
│    ├── Sync Logs (timeline table)                │
│    └── Content Browser (tree navigation)         │
│                                                 │
│  Zustand Store  ←→  API Client                  │
└──────────────────────┬──────────────────────────┘
                       │ HTTP
              ┌────────▼────────┐
              │  POC-09 :8009   │
              │  Connectors API │
              └─────────────────┘
```

## Components

| Component | Description |
|-----------|-------------|
| `SourceIcon` | Maps source types to Lucide icons with category colors |
| `ConnectorCard` | Catalog card with source info, auth badges, connect button |
| `SyncStatusBadge` | Color-coded status pill with animated dot for running |
| `SyncTimeline` | Sync log table with duration, doc counts, error messages |
| `ContentBrowser` | Tree navigation with breadcrumbs, folder/file icons |
| `CredentialForm` | Dynamic credential inputs per auth method and source |

## Files

```
poc-10-data-source-ui/
├── package.json
├── next.config.js
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── README.md
└── src/
    ├── globals.css
    ├── app/
    │   ├── layout.tsx                 # Sidebar + nav
    │   ├── page.tsx                   # Dashboard
    │   ├── catalog/page.tsx           # Source catalog grid
    │   ├── connections/
    │   │   ├── page.tsx              # Connections table
    │   │   └── [id]/page.tsx         # Connection detail (3 tabs)
    │   └── connect/[source]/page.tsx  # 3-step connect wizard
    ├── components/
    │   ├── SourceIcon.tsx
    │   ├── ConnectorCard.tsx
    │   ├── SyncStatusBadge.tsx
    │   ├── SyncTimeline.tsx
    │   ├── ContentBrowser.tsx
    │   └── CredentialForm.tsx
    └── lib/
        ├── types.ts                  # TypeScript types + category metadata
        ├── api.ts                    # API client for POC-09 (:8009)
        └── store.ts                  # Zustand state management
```

## Quick Start

```bash
cd poc/poc-10-data-source-ui
npm install
npm run dev  # → http://localhost:3002
```

Requires POC-09 running on port 8009 for backend API.

## Integration with POC-09

| UI Action | API Call |
|-----------|----------|
| Load catalog | `GET /sources` |
| Connect wizard: create | `POST /connectors` |
| Trigger sync | `POST /connectors/{id}/sync` |
| Browse content | `GET /connectors/{id}/browse?path=...` |
| View sync logs | `GET /connectors/{id}/logs` |
| Test connection | `POST /connectors/{id}/validate` |
| Delete connection | `DELETE /connectors/{id}` |
