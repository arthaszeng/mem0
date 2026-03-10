"""
Async HTTP client for the Concierge chat API.

Handles:
- SHA-256 body hashing (required by AWS CloudFront)
- Cookie-based authentication
- Streaming SSE responses
- Automatic 401 retry after session refresh
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from .stream_parser import ConciergeStreamError, extract_text, stream_text_deltas

CONCIERGE_BASE = "https://concierge.sanofi.com"
CHAT_ENDPOINT = "/api/chat"
REFRESH_ENDPOINT = "/auth/refresh"


def _build_chat_body(
    message: str,
    thread_id: str | None = None,
    timezone: str = "Asia/Shanghai",
) -> dict:
    return {
        "id": thread_id or str(uuid.uuid4()),
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            }
        ],
        "timeZone": timezone,
        "documents": [],
        "trigger": "submit-message",
    }


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ConciergeClient:
    """Stateless client — caller supplies the access_token per request."""

    def __init__(self, base_url: str = CONCIERGE_BASE):
        self.base_url = base_url.rstrip("/")

    async def chat(
        self,
        access_token: str,
        message: str,
        thread_id: str | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> str:
        """Send a message and return the full text response."""
        body = _build_chat_body(message, thread_id, timezone)
        async with self._stream_request(access_token, body) as stream:
            return await extract_text(stream)

    async def chat_stream(
        self,
        access_token: str,
        message: str,
        thread_id: str | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> AsyncIterator[str]:
        """Send a message and yield text deltas as they arrive."""
        body = _build_chat_body(message, thread_id, timezone)
        async with self._stream_request(access_token, body) as stream:
            async for delta in stream_text_deltas(stream):
                yield delta

    async def refresh_session(self, access_token: str) -> str | None:
        """Call POST /auth/refresh and return the new access_token cookie value, or None on failure."""
        empty_hash = _sha256_hex(b"")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.base_url}{REFRESH_ENDPOINT}",
                headers={
                    "Content-Type": "application/json",
                    "x-amz-content-sha256": empty_hash,
                },
                cookies={"access_token": access_token},
            )
        if resp.status_code == 200:
            return resp.cookies.get("access_token") or access_token
        return None

    @asynccontextmanager
    async def _stream_request(
        self,
        access_token: str,
        body: dict,
        _retried: bool = False,
    ):
        """Context manager that yields an async byte iterator for the SSE response.

        Automatically retries once on 401 after refreshing the session.
        """
        body_bytes = json.dumps(body).encode("utf-8")
        sha256 = _sha256_hex(body_bytes)

        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10))
        try:
            req = client.build_request(
                "POST",
                f"{self.base_url}{CHAT_ENDPOINT}",
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "x-amz-content-sha256": sha256,
                },
                cookies={"access_token": access_token},
            )
            resp = await client.send(req, stream=True)

            if resp.status_code == 401 and not _retried:
                await resp.aclose()
                await client.aclose()
                new_token = await self.refresh_session(access_token)
                if new_token:
                    async with self._stream_request(new_token, body, _retried=True) as s:
                        yield s
                    return
                raise ConciergeStreamError("Session expired — re-login required")

            if resp.status_code != 200:
                data = await resp.aread()
                await resp.aclose()
                await client.aclose()
                raise ConciergeStreamError(
                    f"Concierge returned HTTP {resp.status_code}: {data.decode(errors='replace')[:200]}"
                )

            yield resp.aiter_bytes()
            await resp.aclose()
        finally:
            await client.aclose()
