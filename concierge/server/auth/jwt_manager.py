"""
JWT manager for signing and verifying MCP OAuth tokens.

These tokens are issued by our MCP server to Cursor after the user
successfully syncs their Concierge cookies via the Chrome extension.
"""

from __future__ import annotations

import os
import time
import uuid

import jwt

_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
_ALGORITHM = "HS256"
_TOKEN_TTL = 7 * 24 * 3600  # 7 days


def create_access_token(user_id: str) -> str:
    now = time.time()
    payload = {
        "sub": user_id,
        "iat": int(now),
        "exp": int(now + _TOKEN_TTL),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_access_token(token: str) -> dict | None:
    """Return the decoded payload or None if invalid/expired."""
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None


def create_auth_code(user_id: str) -> str:
    """Short-lived auth code for the OAuth code exchange."""
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,  # 5 minutes
        "type": "auth_code",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_auth_code(code: str) -> str | None:
    """Verify an auth code and return user_id, or None."""
    try:
        payload = jwt.decode(code, _SECRET, algorithms=[_ALGORITHM])
        if payload.get("type") != "auth_code":
            return None
        return payload.get("sub")
    except jwt.InvalidTokenError:
        return None
