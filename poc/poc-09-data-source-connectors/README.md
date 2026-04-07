# POC-09 · Data Source Connectors

> **FastAPI connector framework** for 13 external data sources with sync orchestration, content browsing, and OAuth support.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI  (:8009)                                                │
│  /sources · /connectors · /connectors/{id}/sync · /oauth         │
└──────────┬──────────────────────┬────────────────────────────────┘
           │                      │
    ┌──────▼──────┐       ┌──────▼──────┐
    │  Registry   │       │ SyncEngine  │
    │  (factory)  │       │ (async +    │
    │             │       │  semaphore) │
    └──────┬──────┘       └──────┬──────┘
           │                      │
    ┌──────▼──────────────────────▼──────┐
    │  Connector Implementations (13)    │
    │                                    │
    │  BaseConnector + LoadConnector     │
    │               + PollConnector      │
    │               + BrowsableConnector │
    │               + OAuthConnector     │
    └──────┬─────────────────────────────┘
           │
    ┌──────▼──────┐     ┌────────────┐
    │CredManager  │     │ JSON Store │
    │(Fernet enc) │     │(connectors)│
    └─────────────┘     └────────────┘
```

## Supported Data Sources (13)

| Source | Category | Auth Methods | Capabilities |
|--------|----------|-------------|--------------|
| **Amazon S3** | Cloud Storage | Access Key, Service Account | Load, Poll, Browse |
| **Google Cloud Storage** | Cloud Storage | Service Account, OAuth | Load, Poll, Browse |
| **Google Drive** | Cloud Storage | OAuth, Service Account | Load, Poll, Browse, OAuth |
| **Dropbox** | Cloud Storage | OAuth, API Key | Load, Poll, Browse, OAuth |
| **Confluence** | Collaboration | API Key, OAuth | Load, Poll, Browse |
| **Jira** | Project Mgmt | API Key, OAuth | Load, Poll, Browse |
| **Asana** | Project Mgmt | API Key, OAuth | Load, Poll, Browse |
| **Zendesk** | Collaboration | API Key, Basic | Load, Poll, Browse |
| **GitHub** | Dev Tools | API Key, OAuth | Load, Poll, Browse |
| **GitLab** | Dev Tools | API Key | Load, Poll, Browse |
| **Bitbucket** | Dev Tools | App Password, OAuth | Load, Poll, Browse |
| **Discord** | Communication | Bot Token | Load, Poll, Browse |
| **Gmail** | Communication | OAuth | Load, Poll, Browse, OAuth |

## Connector Interfaces

Each connector implements a subset of these mixin ABCs:

- **`BaseConnector`** — `connect()`, `disconnect()`, `validate()`, `source_info()`
- **`LoadConnector`** — `load_from_state()` → full initial load
- **`PollConnector`** — `poll_source(start, end)` → incremental sync
- **`BrowsableConnector`** — `list_content(path)` → content tree browsing
- **`OAuthConnector`** — `get_oauth_url()`, `exchange_code()`, `refresh_token()`

## Files

```
poc-09-data-source-connectors/
├── main.py              # FastAPI application (port 8009)
├── config.py            # Environment configuration
├── models.py            # Pydantic models (SourceDocument, ConnectorConfig, SyncLog, etc.)
├── interfaces.py        # Connector ABCs (BaseConnector, LoadConnector, PollConnector, etc.)
├── registry.py          # Connector registry (factory pattern + @register decorator)
├── credentials.py       # Fernet-encrypted credential storage
├── sync_engine.py       # Async sync orchestrator with semaphore + checkpointing
├── store.py             # JSON-backed connector config persistence
├── requirements.txt     # Python dependencies
├── README.md
└── connectors/
    ├── __init__.py              # Auto-imports all connectors
    ├── s3_connector.py          # Amazon S3 (boto3)
    ├── confluence_connector.py  # Confluence Cloud (REST API v2)
    ├── discord_connector.py     # Discord (Bot API v10)
    ├── google_drive_connector.py # Google Drive (Drive API v3)
    ├── gmail_connector.py       # Gmail (Gmail API v1)
    ├── jira_connector.py        # Jira Cloud (REST API v3)
    ├── dropbox_connector.py     # Dropbox (HTTP API v2)
    ├── gcs_connector.py         # Google Cloud Storage (JSON API v1)
    ├── gitlab_connector.py      # GitLab (REST API v4)
    ├── github_connector.py      # GitHub (REST API)
    ├── bitbucket_connector.py   # Bitbucket Cloud (REST API 2.0)
    ├── zendesk_connector.py     # Zendesk (REST API)
    └── asana_connector.py       # Asana (REST API 1.0)
```

## API Endpoints

### Source Catalog
| Method | Path | Description |
|--------|------|-------------|
| GET | `/sources` | List all 13 available source types |
| GET | `/sources/{type}` | Get source metadata + config schema |

### Connector CRUD
| Method | Path | Description |
|--------|------|-------------|
| POST | `/connectors` | Create connector instance |
| GET | `/connectors` | List all connectors (masked creds) |
| GET | `/connectors/{id}` | Get connector + last sync info |
| PATCH | `/connectors/{id}` | Update config/credentials |
| DELETE | `/connectors/{id}` | Delete connector |

### Sync Operations
| Method | Path | Description |
|--------|------|-------------|
| POST | `/connectors/{id}/sync` | Trigger full or incremental sync |
| POST | `/connectors/{id}/cancel` | Cancel running sync |
| GET | `/connectors/{id}/logs` | Get sync execution logs |
| GET | `/connectors/{id}/status` | Get current sync status + checkpoint |

### Content Browsing
| Method | Path | Description |
|--------|------|-------------|
| GET | `/connectors/{id}/browse` | Browse source content tree |

### Validation & OAuth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/connectors/{id}/validate` | Test connection |
| GET | `/oauth/{type}/authorize` | Get OAuth URL |
| POST | `/oauth/{type}/callback` | Exchange OAuth code |

## Quick Start

```bash
cd poc/poc-09-data-source-connectors
pip install -r requirements.txt

# Set credentials for your sources (examples)
export AWS_ACCESS_KEY_ID=...
export GITHUB_TOKEN=...

python main.py  # → http://localhost:8009
```

### Create a GitHub connector
```bash
curl -X POST http://localhost:8009/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My GitHub Repos",
    "source_type": "github",
    "auth_method": "api_key",
    "credentials": {"api_token": "ghp_..."},
    "config": {"repos": ["owner/repo"], "include_issues": true}
  }'
```

### Trigger sync
```bash
curl -X POST http://localhost:8009/connectors/{id}/sync
```

### Browse content
```bash
curl http://localhost:8009/connectors/{id}/browse?path=owner/repo
```

## Data Flow → POC-01

```
External Source → Connector.load/poll → SourceDocument batches
                                           ↓
                                    POST to POC-01 pipeline
                                    (document processing)
                                           ↓
                                    Chunks → Embeddings → Qdrant
```

## Key Patterns

1. **Factory + Registry**: `@register(SourceType.XYZ)` decorator auto-registers connectors
2. **Mixin Interfaces**: Compose capabilities (`LoadConnector + PollConnector + BrowsableConnector`)
3. **Encrypted Credentials**: Fernet-encrypted at rest, masked in API responses
4. **Checkpoint Sync**: Each connector maintains a `SyncCheckpoint` for incremental polling
5. **Semaphore-bounded Execution**: `SyncEngine` limits concurrent syncs
6. **Cooperative Cancellation**: Running syncs check if they're still in `_running` set
