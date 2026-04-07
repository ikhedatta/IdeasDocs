"""Connector configuration."""

import os

# ── API ────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8009"))

# ── Credential encryption key (Fernet, 32-byte base64-encoded) ─────────
CREDENTIAL_ENCRYPTION_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")

# ── Database (JSON file for POC — swap for PostgreSQL in production) ──
DATA_DIR = os.getenv("DATA_DIR", "./data")

# ── Downstream pipeline (POC-01) endpoint ─────────────────────────────
PIPELINE_URL = os.getenv("PIPELINE_URL", "http://localhost:8001")

# ── Sync defaults ─────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE = int(os.getenv("DEFAULT_BATCH_SIZE", "50"))
MAX_CONCURRENT_SYNCS = int(os.getenv("MAX_CONCURRENT_SYNCS", "4"))
SYNC_TIMEOUT_SECONDS = int(os.getenv("SYNC_TIMEOUT_SECONDS", "600"))

# ── OAuth (shared) ────────────────────────────────────────────────────
OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8009")

# ── Source-specific env vars ──────────────────────────────────────────
# AWS / S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Google (Drive, Gmail, GCS)
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# Confluence / Jira (Atlassian)
ATLASSIAN_EMAIL = os.getenv("ATLASSIAN_EMAIL", "")
ATLASSIAN_API_TOKEN = os.getenv("ATLASSIAN_API_TOKEN", "")
ATLASSIAN_CLOUD_URL = os.getenv("ATLASSIAN_CLOUD_URL", "")

# Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Dropbox
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")

# GitLab
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.com")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Bitbucket
BITBUCKET_USERNAME = os.getenv("BITBUCKET_USERNAME", "")
BITBUCKET_APP_PASSWORD = os.getenv("BITBUCKET_APP_PASSWORD", "")

# Zendesk
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL", "")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN", "")

# Asana
ASANA_ACCESS_TOKEN = os.getenv("ASANA_ACCESS_TOKEN", "")
