"""OAuth 2.1 Authorization Server endpoints.

Implements: Authorization Server Metadata, Dynamic Client Registration,
Authorization endpoint, Token endpoint, JWKS, Token Revocation,
and Protected Resource Metadata for MCP."""

import hashlib
import json
import secrets
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel as _BaseModel
from sqlalchemy.orm import Session

from config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    AUTH_BASE_URL,
    AUTH_CODE_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
)
from database import get_db
from jwt_utils import get_jwks, sign_access_token
from models import AuthorizationCode, OAuthClient, RefreshToken, User
from schemas import OAuthClientRegistrationRequest, TokenRequest

router = APIRouter(prefix="/auth", tags=["oauth"])
templates = Jinja2Templates(directory="templates")


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata():
    return {
        "issuer": AUTH_BASE_URL,
        "authorization_endpoint": f"{AUTH_BASE_URL}/authorize",
        "token_endpoint": f"{AUTH_BASE_URL}/token",
        "registration_endpoint": f"{AUTH_BASE_URL}/register",
        "jwks_uri": f"{AUTH_BASE_URL}/jwks",
        "revocation_endpoint": f"{AUTH_BASE_URL}/token/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
    }


@router.get("/resource-metadata/{service_name}")
def protected_resource_metadata(service_name: str, request: Request):
    scheme = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("Host", "localhost")
    base = f"{scheme}://{host}"
    return {
        "resource": f"{base}/{service_name}/",
        "authorization_servers": [f"{base}/auth/"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp:read", "mcp:write"],
    }


@router.post("/register")
def register_client(body: OAuthClientRegistrationRequest, db: Session = Depends(get_db)):
    client_id = secrets.token_urlsafe(24)
    client = OAuthClient(
        client_id=client_id,
        client_name=body.client_name or f"dynamic-{client_id[:8]}",
        redirect_uris=json.dumps(body.redirect_uris),
        grant_types=json.dumps(body.grant_types),
        is_dynamic=True,
    )
    db.add(client)
    db.commit()
    return {
        "client_id": client_id,
        "client_name": client.client_name,
        "redirect_uris": body.redirect_uris,
        "grant_types": body.grant_types,
        "token_endpoint_auth_method": body.token_endpoint_auth_method,
    }


@router.get("/authorize")
def authorize(
    request: Request,
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    scope: str = "",
    db: Session = Depends(get_db),
):
    if response_type != "code":
        raise HTTPException(400, "Only response_type=code is supported")

    client = db.query(OAuthClient).filter(OAuthClient.client_id == client_id).first()
    if not client:
        raise HTTPException(400, f"Unknown client_id: {client_id}")

    allowed_uris = json.loads(client.redirect_uris)
    if not allowed_uris:
        raise HTTPException(400, "No redirect_uris configured for this client")
    if redirect_uri not in allowed_uris:
        raise HTTPException(400, "redirect_uri not registered for this client")

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "scope": scope,
            "client_name": client.client_name,
            "error": "",
        },
    )


@router.post("/authorize")
def authorize_submit(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle login form submission during OAuth flow."""
    import asyncio
    loop = asyncio.get_event_loop()
    # We need to await the form() coroutine
    return _authorize_submit_sync(request, db)


async def _authorize_submit_async(request: Request, db: Session):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    client_id = form.get("client_id", "")
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    code_challenge = form.get("code_challenge", "")
    code_challenge_method = form.get("code_challenge_method", "S256")
    scope = form.get("scope", "")

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
        client = db.query(OAuthClient).filter(OAuthClient.client_id == client_id).first()
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
                "scope": scope,
                "client_name": client.client_name if client else "",
                "error": "Invalid username or password",
            },
        )

    raw_code = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(raw_code.encode()).hexdigest()

    auth_code = AuthorizationCode(
        code_hash=code_hash,
        client_id=client_id,
        user_id=user.id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scopes=scope,
        expires_at=datetime.now(UTC) + timedelta(seconds=AUTH_CODE_EXPIRE_SECONDS),
    )
    db.add(auth_code)
    db.commit()

    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={raw_code}"
    if state:
        location += f"&state={state}"
    return RedirectResponse(url=location, status_code=302)


# Replace the sync POST handler with async
router.routes = [r for r in router.routes if not (hasattr(r, 'path') and r.path == "/auth/authorize" and hasattr(r, 'methods') and 'POST' in r.methods)]


@router.post("/authorize", response_class=HTMLResponse)
async def authorize_post(request: Request, db: Session = Depends(get_db)):
    return await _authorize_submit_async(request, db)


def _verify_pkce(code_challenge: str, code_verifier: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return computed == code_challenge


@router.post("/token")
def token(body: TokenRequest, db: Session = Depends(get_db)):
    if body.grant_type == "authorization_code":
        return _handle_authorization_code(body, db)
    elif body.grant_type == "refresh_token":
        return _handle_refresh_token(body, db)
    else:
        raise HTTPException(400, f"Unsupported grant_type: {body.grant_type}")


def _handle_authorization_code(body: TokenRequest, db: Session):
    if not body.code or not body.client_id:
        raise HTTPException(400, "code and client_id required")

    client = db.query(OAuthClient).filter(OAuthClient.client_id == body.client_id).first()
    if not client:
        raise HTTPException(400, "Unknown client_id")
    if client.client_secret_hash:
        if not body.client_secret:
            raise HTTPException(400, "client_secret required for this client")
        if not bcrypt.checkpw(body.client_secret.encode(), client.client_secret_hash.encode()):
            raise HTTPException(400, "Invalid client_secret")

    code_hash = hashlib.sha256(body.code.encode()).hexdigest()
    auth_code = db.query(AuthorizationCode).filter(
        AuthorizationCode.code_hash == code_hash,
        AuthorizationCode.used == False,
    ).first()

    if not auth_code:
        raise HTTPException(400, "Invalid authorization code")
    if auth_code.expires_at < datetime.now(UTC):
        raise HTTPException(400, "Authorization code expired")
    if auth_code.client_id != body.client_id:
        raise HTTPException(400, "client_id mismatch")
    if auth_code.redirect_uri and body.redirect_uri != auth_code.redirect_uri:
        raise HTTPException(400, "redirect_uri mismatch")

    if auth_code.code_challenge:
        if not body.code_verifier:
            raise HTTPException(400, "code_verifier required for PKCE")
        if not _verify_pkce(auth_code.code_challenge, body.code_verifier):
            raise HTTPException(400, "PKCE verification failed")

    auth_code.used = True

    user = db.query(User).filter(User.id == auth_code.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(400, "User not found or inactive")

    access_token = sign_access_token(
        user_id=user.id,
        username=user.username,
        is_superadmin=user.is_superadmin,
        issuer=AUTH_BASE_URL,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS,
    )

    raw_refresh = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    rt = RefreshToken(
        token_hash=refresh_hash,
        user_id=user.id,
        client_id=body.client_id,
        scopes=auth_code.scopes,
        expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_EXPIRE_SECONDS),
    )
    db.add(rt)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
        "refresh_token": raw_refresh,
    }


def _handle_refresh_token(body: TokenRequest, db: Session):
    if not body.refresh_token:
        raise HTTPException(400, "refresh_token required")

    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    rt = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
    ).first()

    if not rt or rt.expires_at < datetime.now(UTC):
        raise HTTPException(400, "Invalid or expired refresh token")

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(400, "User not found or inactive")

    rt.revoked = True

    access_token = sign_access_token(
        user_id=user.id,
        username=user.username,
        is_superadmin=user.is_superadmin,
        issuer=AUTH_BASE_URL,
        expires_in=ACCESS_TOKEN_EXPIRE_SECONDS,
    )

    raw_refresh = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    new_rt = RefreshToken(
        token_hash=refresh_hash,
        user_id=user.id,
        client_id=rt.client_id,
        scopes=rt.scopes,
        expires_at=datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_EXPIRE_SECONDS),
    )
    db.add(new_rt)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
        "refresh_token": raw_refresh,
    }


class RevokeTokenRequest(_BaseModel):
    token: str


@router.post("/token/revoke")
def revoke_token(body: RevokeTokenRequest, db: Session = Depends(get_db)):
    if not body.token:
        return {"message": "ok"}
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if rt:
        rt.revoked = True
        db.commit()
    return {"message": "ok"}


@router.get("/jwks")
def jwks():
    return get_jwks()
