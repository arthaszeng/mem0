"""
Parser for Vercel AI SDK Data Stream protocol.

The Concierge API returns SSE lines like:
  data: {"type":"text-delta","id":"0","delta":"Hello"}
  data: {"type":"finish","finishReason":"stop"}
  data: [DONE]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class StreamEvent:
    type: str
    data: dict | str | None = None


class ConciergeStreamError(Exception):
    pass


async def parse_sse_stream(
    byte_stream: AsyncIterator[bytes],
) -> AsyncIterator[StreamEvent]:
    """Parse raw SSE byte chunks into StreamEvent objects."""
    buffer = ""
    async for chunk in byte_stream:
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                continue
            event = _parse_line(line)
            if event is not None:
                yield event


async def extract_text(byte_stream: AsyncIterator[bytes]) -> str:
    """Consume a Concierge SSE stream and return the full text response."""
    parts: list[str] = []
    async for event in parse_sse_stream(byte_stream):
        if event.type == "text-delta" and isinstance(event.data, dict):
            parts.append(event.data.get("delta", ""))
        elif event.type == "error" and isinstance(event.data, dict):
            raise ConciergeStreamError(event.data.get("errorText", "Unknown error"))
        elif event.type == "done":
            break
    return "".join(parts)


async def stream_text_deltas(
    byte_stream: AsyncIterator[bytes],
) -> AsyncIterator[str]:
    """Yield text delta strings as they arrive."""
    async for event in parse_sse_stream(byte_stream):
        if event.type == "text-delta" and isinstance(event.data, dict):
            delta = event.data.get("delta", "")
            if delta:
                yield delta
        elif event.type == "error" and isinstance(event.data, dict):
            raise ConciergeStreamError(event.data.get("errorText", "Unknown error"))
        elif event.type == "done":
            return


def _parse_line(line: str) -> StreamEvent | None:
    if not line.startswith("data: "):
        return None
    payload = line[6:]
    if payload == "[DONE]":
        return StreamEvent(type="done")
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return StreamEvent(type=obj.get("type", "unknown"), data=obj)
