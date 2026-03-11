"""
OAuth 2.1 endpoints for MCP authentication.

Implements the subset of OAuth 2.1 required by the MCP spec:
- Discovery (.well-known/oauth-authorization-server)
- Dynamic client registration
- Authorization (serves the login page)
- Cookie sync (receives cookies from Chrome extension)
- Token exchange (auth_code -> access_token)
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from . import jwt_manager
from .cookie_store import cookie_store

router = APIRouter()

_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8766")

# In-memory stores for OAuth state
_registered_clients: dict[str, dict] = {}
# Maps state -> {redirect_uri, code_challenge, user_id (set after cookie sync)}
_pending_authorizations: dict[str, dict] = {}


@router.get("/.well-known/oauth-authorization-server")
async def oauth_discovery():
    return {
        "issuer": _SERVER_URL,
        "authorization_endpoint": f"{_SERVER_URL}/auth/authorize",
        "token_endpoint": f"{_SERVER_URL}/auth/token",
        "registration_endpoint": f"{_SERVER_URL}/auth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@router.post("/auth/register")
async def register_client(request: Request):
    body = await request.json()
    client_id = str(uuid.uuid4())
    _registered_clients[client_id] = {
        "client_name": body.get("client_name", "unknown"),
        "redirect_uris": body.get("redirect_uris", []),
    }
    return {
        "client_id": client_id,
        "client_name": body.get("client_name", "unknown"),
        "redirect_uris": body.get("redirect_uris", []),
    }


@router.get("/auth/authorize")
async def authorize(
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
):
    """Serve the authorization page. The page handles SSO + extension cookie sync."""
    _pending_authorizations[state] = {
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "user_id": None,
        "auth_code": None,
    }
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    return FileResponse(os.path.join(static_dir, "authorize.html"))


@router.post("/auth/cookies")
async def receive_cookies(request: Request):
    """Receive Concierge cookies from the Chrome extension.

    Body: { "state": "<oauth-state>", "access_token": "<jwt>" }

    When called through the auth gateway (Extension popup with API key),
    X-Auth-Username is injected and used as the cookie_store key so it
    matches the key used during MCP tool execution.
    Fallback to Sanofi JWT sub for the OAuth authorize page flow.
    """
    body = await request.json()
    state = body.get("state")
    access_token = body.get("access_token")

    if not access_token:
        raise HTTPException(400, "Missing access_token")

    gateway_username = request.headers.get("X-Auth-Username")
    if gateway_username:
        user_id = gateway_username
    else:
        user_id = _extract_user_id(access_token)
    cookie_store.set(user_id, access_token)

    pending = _pending_authorizations.get(state) if state else None

    auth_code = jwt_manager.create_auth_code(user_id)

    if pending:
        pending["user_id"] = user_id
        pending["auth_code"] = auth_code
        redirect_uri = pending["redirect_uri"]
    else:
        redirect_uri = _SERVER_URL

    return {
        "ok": True,
        "redirect_url": f"{redirect_uri}?code={auth_code}&state={state or ''}",
    }


@router.post("/auth/token")
async def token_exchange(request: Request):
    """Exchange an auth code (+ code_verifier) for an MCP access token."""
    body = await request.form()
    grant_type = body.get("grant_type")
    code = body.get("code")
    code_verifier = body.get("code_verifier")

    if grant_type != "authorization_code":
        raise HTTPException(400, "Unsupported grant_type")

    user_id = jwt_manager.verify_auth_code(code)
    if user_id is None:
        raise HTTPException(400, "Invalid or expired auth code")

    # PKCE is optional but if provided we validate it
    # (find the pending auth by scanning for matching auth_code)
    for _state, pending in _pending_authorizations.items():
        if pending.get("auth_code") == code:
            if code_verifier and pending.get("code_challenge"):
                expected = (
                    hashlib.sha256(code_verifier.encode())
                    .digest()
                )
                import base64
                expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
                if expected_b64 != pending["code_challenge"]:
                    raise HTTPException(400, "PKCE verification failed")
            _pending_authorizations.pop(_state, None)
            break

    access_token = jwt_manager.create_access_token(user_id)
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 7 * 24 * 3600,
    })


def _extract_user_id(concierge_jwt: str) -> str:
    """Extract a user identifier from the Concierge JWT without verifying its signature."""
    import base64
    import json

    parts = concierge_jwt.split(".")
    if len(parts) < 2:
        return f"user-{secrets.token_hex(8)}"
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub", payload.get("properties", {}).get("id", f"user-{secrets.token_hex(8)}"))
    except Exception:
        return f"user-{secrets.token_hex(8)}"
