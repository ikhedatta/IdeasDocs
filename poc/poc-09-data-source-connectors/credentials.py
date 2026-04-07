"""Credential management with optional Fernet encryption."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_FERNET = None


def _get_fernet():
    """Lazy-init Fernet cipher.  Falls back to no-op if key isn't set."""
    global _FERNET
    if _FERNET is not None:
        return _FERNET

    key = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    if not key:
        logger.warning("CREDENTIAL_ENCRYPTION_KEY not set — credentials stored unencrypted")
        return None

    try:
        from cryptography.fernet import Fernet

        _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
        return _FERNET
    except Exception:
        logger.warning("Failed to initialise Fernet — credentials stored unencrypted")
        return None


def encrypt_credentials(creds: dict[str, Any]) -> str:
    """Encrypt credential dict → base64 string.  Pass-through if no key."""
    raw = json.dumps(creds, default=str).encode()
    f = _get_fernet()
    if f is None:
        return base64.b64encode(raw).decode()
    return f.encrypt(raw).decode()


def decrypt_credentials(token: str) -> dict[str, Any]:
    """Decrypt credential string → dict.  Pass-through if no key."""
    f = _get_fernet()
    if f is None:
        return json.loads(base64.b64decode(token.encode()))
    return json.loads(f.decrypt(token.encode()))


def mask_credentials(creds: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secret values masked for API responses."""
    masked = {}
    secret_keys = {"password", "secret", "token", "api_key", "access_key",
                   "secret_key", "refresh_token", "private_key", "app_password"}
    for k, v in creds.items():
        if any(sk in k.lower() for sk in secret_keys):
            if isinstance(v, str) and len(v) > 8:
                masked[k] = v[:4] + "****" + v[-4:]
            else:
                masked[k] = "****"
        else:
            masked[k] = v
    return masked
