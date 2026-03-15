"""
Concierge MCP Server — wraps the Sanofi Concierge AI (Claude 4 Sonnet)
with SSE + Streamable HTTP transport for Cursor IDE.

Authentication is handled entirely by the nginx gateway (Auth Service),
which injects X-Auth-Username into every request.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport

from .auth.cookie_store import cookie_store
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
        raise ConciergeStreamError("Not authenticated — no user context available")
    token = cookie_store.get(uid)
    if not token and _is_dev_mode():
        token = cookie_store.get_any()
    if not token:
        raise ConciergeStreamError("No Concierge session — sync cookies via Chrome extension first")
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

_app_version = os.getenv("APP_VERSION", "dev")
app = FastAPI(title="Concierge MCP Server", version=_app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get(f"{_PREFIX}/health")
async def health():
    return {"status": "ok", "service": "concierge-mcp", "version": _app_version}


@app.get(f"{_PREFIX}/auth/status")
async def auth_status(request: Request):
    """Check if a valid Concierge session is available for the current user."""
    username = _get_username(request)
    token = cookie_store.get(username)
    return {"connected": token is not None, "user": username}


@app.post(f"{_PREFIX}/auth/cookies")
async def receive_cookies(request: Request):
    """Receive Concierge cookies from the Chrome extension.

    Requires gateway authentication — X-Auth-Username is injected by nginx.
    """
    username = _get_username(request)
    body = await request.json()
    access_token = body.get("access_token")
    if not access_token:
        return JSONResponse(status_code=400, content={"error": "Missing access_token"})
    cookie_store.set(username, access_token)
    logger.info("Concierge cookie synced for user=%s", username)
    return {"ok": True, "user": username}


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


# ---------- Streamable HTTP session management ----------

_streamable_sessions: dict[str, StreamableHTTPServerTransport] = {}
_streamable_tasks: dict[str, asyncio.Task] = {}


async def _streamable_session_lifecycle(
    transport: StreamableHTTPServerTransport,
    uid: str,
    ready: asyncio.Event,
):
    """Long-lived background task: keeps transport connected and MCP server running."""
    user_id_var.set(uid)
    try:
        async with transport.connect() as (r, w):
            ready.set()
            await mcp._mcp_server.run(r, w, mcp._mcp_server.create_initialization_options())
    except asyncio.CancelledError:
        pass
    finally:
        sid = transport.mcp_session_id
        if sid:
            _streamable_sessions.pop(sid, None)
            _streamable_tasks.pop(sid, None)


async def _run_streamable_session(request: Request, uid: str):
    """Handle a single Streamable HTTP request, creating or reusing a persistent session."""
    session_id = request.headers.get("mcp-session-id")

    if session_id and session_id in _streamable_sessions:
        transport = _streamable_sessions[session_id]
        await transport.handle_request(request.scope, request.receive, request._send)
        return

    transport = StreamableHTTPServerTransport(mcp_session_id=str(uuid.uuid4()))
    ready = asyncio.Event()
    task = asyncio.create_task(
        _streamable_session_lifecycle(transport, uid, ready)
    )
    await ready.wait()

    sid = transport.mcp_session_id
    if sid:
        _streamable_sessions[sid] = transport
        _streamable_tasks[sid] = task

    await transport.handle_request(request.scope, request.receive, request._send)

    if transport.mcp_session_id and transport.mcp_session_id not in _streamable_sessions:
        _streamable_sessions[transport.mcp_session_id] = transport
        _streamable_tasks[transport.mcp_session_id] = task


# ---------- MCP endpoints (SSE + Streamable HTTP) ----------

@app.api_route(f"{_PREFIX}/sse", methods=["GET", "POST", "DELETE"])
async def handle_mcp(request: Request):
    """Unified MCP endpoint: POST → Streamable HTTP, GET → SSE (legacy)."""
    uid = _get_username(request)

    if request.method == "POST":
        await _run_streamable_session(request, uid)
        return

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
    """Legacy SSE message endpoint."""
    uid = _get_username(request)
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


def _is_dev_mode() -> bool:
    return os.getenv("MCP_DEV_MODE", "").lower() in ("true", "1", "yes")


def _get_username(request: Request) -> str:
    """Extract username from gateway-injected header, or fallback to dev-user."""
    username = request.headers.get("X-Auth-Username")
    if username:
        return username
    if _is_dev_mode():
        return "dev-user"
    raise ConciergeStreamError("Not authenticated — missing X-Auth-Username header")


# ---------- REST API (for ChatGPT Actions / non-MCP clients) ----------

@app.post(f"{_PREFIX}/api/chat")
async def api_chat(request: Request):
    """REST endpoint: chat with Concierge AI. Requires an active session (via Chrome extension)."""
    username = _get_username(request)
    body = await request.json()
    message = body.get("message", "")
    thread_id = body.get("thread_id", "")
    if not message:
        return JSONResponse(status_code=400, content={"error": "Missing 'message' field"})

    token = cookie_store.get(username)
    if not token:
        return JSONResponse(status_code=401, content={"error": "No active Concierge session. Sync cookies via Chrome extension first."})

    try:
        result = await concierge.chat(token, message, thread_id=thread_id or None)
        return {"response": result, "thread_id": thread_id}
    except ConciergeStreamError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})


@app.post(f"{_PREFIX}/api/search")
async def api_search(request: Request):
    """REST endpoint: search Sanofi knowledge base via Concierge AI."""
    username = _get_username(request)
    body = await request.json()
    query = body.get("query", "")
    if not query:
        return JSONResponse(status_code=400, content={"error": "Missing 'query' field"})

    token = cookie_store.get(username)
    if not token:
        return JSONResponse(status_code=401, content={"error": "No active Concierge session. Sync cookies via Chrome extension first."})

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
