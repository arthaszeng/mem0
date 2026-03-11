"""
Concierge MCP Server — wraps the Sanofi Concierge AI (Claude 4 Sonnet)
with OAuth 2.1 authentication and SSE transport for Cursor IDE.
"""

from __future__ import annotations

import contextvars
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport

from .auth import jwt_manager
from .auth.cookie_store import cookie_store
from .auth.oauth_endpoints import router as oauth_router
from .client import ConciergeClient
from .stream_parser import ConciergeStreamError

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("concierge-mcp")

# ---------- Path prefix (must match nginx location for SSE routing) ----------
_PREFIX = "/concierge-mcp"

# ---------- MCP setup ----------
mcp = FastMCP("concierge-mcp")
sse = SseServerTransport(f"{_PREFIX}/msg/")

user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id")

concierge = ConciergeClient(
    base_url=os.getenv("CONCIERGE_BASE_URL", "https://concierge.sanofi.com")
)


def _get_access_token() -> str:
    uid = user_id_var.get(None)
    if not uid:
        raise ConciergeStreamError("Not authenticated — connect via OAuth first")
    token = cookie_store.get(uid)
    if not token and _is_dev_mode():
        token = cookie_store.get_any()
    if not token:
        raise ConciergeStreamError("Session expired — please re-authenticate")
    return token


# ---------- MCP tools ----------

@mcp.tool(
    description="Send a message to the Sanofi Concierge AI assistant (powered by Claude 4 Sonnet). "
    "Use this to ask questions about Sanofi internal knowledge, policies, procedures, or any general topic. "
    "Returns the full text response."
)
async def concierge_chat(message: str, thread_id: str = "") -> str:
    """Chat with Concierge AI."""
    token = _get_access_token()
    tid = thread_id if thread_id else None
    return await concierge.chat(token, message, thread_id=tid)


@mcp.tool(
    description="Search Sanofi internal knowledge base via Concierge AI. "
    "The query is sent to Concierge which searches across OneSupport, SharePoint, QualiPSO, and other company resources."
)
async def concierge_search(query: str) -> str:
    """Search via Concierge AI."""
    token = _get_access_token()
    search_prompt = f"Search for: {query}\n\nPlease provide a concise summary of the most relevant results."
    return await concierge.chat(token, search_prompt)


# ---------- FastAPI app ----------

app = FastAPI(title="Concierge MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount OAuth endpoints under prefix
app.include_router(oauth_router, prefix=_PREFIX)


@app.get(f"{_PREFIX}/auth/extension-id")
async def get_extension_id():
    ext_id = os.getenv("CHROME_EXTENSION_ID", "")
    return {"extension_id": ext_id}


@app.get(f"{_PREFIX}/auth/status")
async def auth_status(request: Request):
    """Check if a valid Concierge session is available for the current user."""
    username = request.headers.get("X-Auth-Username")
    if username:
        token = cookie_store.get(username)
        return {"connected": token is not None, "user": username}
    token = cookie_store.get_any()
    return {"connected": token is not None}


@app.post(f"{_PREFIX}/auth/set-token")
async def set_token(request: Request):
    """Dev endpoint: manually inject a Concierge access_token into the cookie store."""
    if not _is_dev_mode():
        return JSONResponse(status_code=403, content={"error": "Only available in dev mode"})
    body = await request.json()
    token = body.get("access_token", "")
    if not token:
        return JSONResponse(status_code=400, content={"error": "Missing access_token"})
    cookie_store.set("dev-user", token)
    logger.info("Concierge access_token injected for dev-user")
    return {"ok": True, "user_id": "dev-user"}


# ---------- SSE endpoints ----------

@app.get(f"{_PREFIX}/sse")
async def handle_sse(request: Request):
    """Main SSE endpoint for MCP connections."""
    uid = _authenticate_request(request)
    token = user_id_var.set(uid)

    try:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await mcp._mcp_server.run(
                read_stream,
                write_stream,
                mcp._mcp_server.create_initialization_options(),
            )
    finally:
        user_id_var.reset(token)


@app.post(f"{_PREFIX}/msg/")
async def handle_post_message(request: Request):
    uid = _authenticate_request(request)
    token = user_id_var.set(uid)

    try:
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            return {}

        await sse.handle_post_message(request.scope, receive, send)
        return {"status": "ok"}
    finally:
        user_id_var.reset(token)


_DEV_SECRETS = {"dev-secret-change-me", "change-me-to-a-random-secret"}


def _is_dev_mode() -> bool:
    if os.getenv("MCP_DEV_MODE", "").lower() in ("true", "1", "yes"):
        return True
    return os.getenv("JWT_SECRET", "dev-secret-change-me") in _DEV_SECRETS


def _authenticate_request(request: Request) -> str:
    """Extract user_id from gateway headers (preferred) or Bearer token fallback."""
    gateway_username = request.headers.get("X-Auth-Username")
    if gateway_username:
        return gateway_username

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = jwt_manager.verify_access_token(token)
        if payload and "sub" in payload:
            return payload["sub"]
    if _is_dev_mode():
        return "dev-user"
    raise ConciergeStreamError("Invalid or missing authentication token")


# ---------- REST API (for ChatGPT Actions / non-MCP clients) ----------

@app.post(f"{_PREFIX}/api/chat")
async def api_chat(request: Request):
    """REST endpoint: chat with Concierge AI. Requires an active session (via Chrome extension)."""
    body = await request.json()
    message = body.get("message", "")
    thread_id = body.get("thread_id", "")
    if not message:
        return JSONResponse(status_code=400, content={"error": "Missing 'message' field"})

    token = cookie_store.get_any()
    if not token:
        return JSONResponse(status_code=401, content={"error": "No active Concierge session. Authenticate via Chrome extension first."})

    try:
        result = await concierge.chat(token, message, thread_id=thread_id or None)
        return {"response": result, "thread_id": thread_id}
    except ConciergeStreamError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@app.post(f"{_PREFIX}/api/search")
async def api_search(request: Request):
    """REST endpoint: search Sanofi knowledge base via Concierge AI."""
    body = await request.json()
    query = body.get("query", "")
    if not query:
        return JSONResponse(status_code=400, content={"error": "Missing 'query' field"})

    token = cookie_store.get_any()
    if not token:
        return JSONResponse(status_code=401, content={"error": "No active Concierge session. Authenticate via Chrome extension first."})

    try:
        search_prompt = f"Search for: {query}\n\nPlease provide a concise summary of the most relevant results."
        result = await concierge.chat(token, search_prompt)
        return {"response": result, "query": query}
    except ConciergeStreamError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


# ---------- Error handler ----------

@app.exception_handler(ConciergeStreamError)
async def concierge_error_handler(request: Request, exc: ConciergeStreamError):
    return JSONResponse(status_code=502, content={"error": str(exc)})


# ---------- Main ----------

def main():
    import uvicorn
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8766"))
    logger.info(f"Starting Concierge MCP Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
