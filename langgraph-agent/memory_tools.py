"""Memverse tools for LangGraph agent — search and store memories via REST API."""

import os

import httpx
from langchain_core.tools import tool

MEMVERSE_API = os.getenv("MEMVERSE_API", "http://memverse-mcp:8765")
DEFAULT_USER = "arthaszeng"


@tool
def search_memory(query: str, user_id: str = DEFAULT_USER, limit: int = 5) -> str:
    """Search long-term memories by semantic similarity. Use when you need context about the user."""
    resp = httpx.post(
        f"{MEMVERSE_API}/api/v1/memories/search",
        json={"query": query, "user_id": user_id, "limit": limit, "threshold": 0.1},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return "No relevant memories found."
    lines = []
    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        lines.append(f"{i}. {r['memory']} (score: {score:.0%})")
    return "\n".join(lines)


@tool
def store_memory(text: str, user_id: str = DEFAULT_USER) -> str:
    """Store important information in long-term memory. Use for facts, decisions, preferences worth remembering."""
    resp = httpx.post(
        f"{MEMVERSE_API}/api/v1/memories/",
        json={
            "text": text,
            "user_id": user_id,
            "infer": True,
            "app": "langgraph-agent",
            "metadata": {"source_app": "langgraph-agent"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content", data.get("text", ""))
    return f"Stored: {content}" if content else "Memory stored."


@tool
def list_memories(user_id: str = DEFAULT_USER, limit: int = 20) -> str:
    """List all stored memories for the user."""
    resp = httpx.get(
        f"{MEMVERSE_API}/api/v1/memories/",
        params={"user_id": user_id, "size": limit},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return "No memories stored."
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item.get('content', '')} (id: {item['id']})")
    return "\n".join(lines)


ALL_TOOLS = [search_memory, store_memory, list_memories]
