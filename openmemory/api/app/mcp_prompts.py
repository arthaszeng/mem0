"""
MCP Prompts for OpenMemory.

Dynamic prompt templates that pull live data from the memory system.
Cursor (and other MCP clients) can invoke these to inject contextual
knowledge into conversations without manual tool calls.
"""

import asyncio
import datetime
import json
import logging

from app.database import SessionLocal
from app.models import Memory, MemoryState
from app.utils.domain_registry import get_domains
from app.utils.memory import get_memory_client

logger = logging.getLogger(__name__)


def _get_memory_client_safe():
    try:
        return get_memory_client()
    except Exception as e:
        logger.warning(f"Prompt: failed to get memory client: {e}")
        return None


def _search_memories_sync(client, query: str, user_id: str, limit: int = 50):
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    emb = client.embedding_model.embed(query, "search")
    qf = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
    return client.vector_store.client.query_points(
        collection_name=client.vector_store.collection_name,
        query=emb,
        query_filter=qf,
        limit=limit,
    ).points


def _format_memory_list(memories: list[dict], heading: str = "Memories") -> str:
    if not memories:
        return f"No {heading.lower()} found."
    lines = [f"## {heading} ({len(memories)} items)\n"]
    for i, m in enumerate(memories, 1):
        score_str = f" (relevance: {m['score']:.2f})" if m.get("score") else ""
        date_str = ""
        for key in ("updated_at", "created_at"):
            if m.get(key):
                date_str = f" [{m[key][:10]}]"
                break
        lines.append(f"{i}. {m.get('memory', '(empty)')}{score_str}{date_str}")
    return "\n".join(lines)


def register_prompts(mcp, user_id_var, client_name_var):
    """Register all MCP prompts on the given FastMCP instance."""

    @mcp.prompt(
        name="recall",
        description="Recall relevant memories about a topic. "
        "Use this to load context before starting a conversation.",
    )
    async def recall(topic: str) -> str:
        uid = user_id_var.get(None) or "arthaszeng"
        client = _get_memory_client_safe()
        if not client:
            return "Memory system unavailable. Please try again later."

        hits = await asyncio.to_thread(_search_memories_sync, client, topic, uid, 50)

        results = []
        for h in hits:
            payload = h.payload or {}
            results.append({
                "memory": payload.get("data", ""),
                "score": h.score,
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
            })

        header = (
            f"Below are memories relevant to **{topic}**. "
            "Use them as context for the conversation — do not repeat them verbatim.\n\n"
        )
        return header + _format_memory_list(results, f"Memories about '{topic}'")

    @mcp.prompt(
        name="briefing",
        description="Generate a session briefing: recent memories, active projects, "
        "and pending items. Great for starting a work session.",
    )
    async def briefing() -> str:
        uid = user_id_var.get(None) or "arthaszeng"
        db = SessionLocal()
        try:
            from app.utils.db import get_user_and_app
            user, _ = get_user_and_app(db, user_id=uid, app_id="cursor")

            cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7)
            recent = (
                db.query(Memory)
                .filter(
                    Memory.user_id == user.id,
                    Memory.state == MemoryState.active,
                    Memory.updated_at >= cutoff,
                )
                .order_by(Memory.updated_at.desc())
                .limit(30)
                .all()
            )

            domains = get_domains()
            by_domain: dict[str, list[str]] = {}
            uncategorized = []
            for m in recent:
                meta = m.metadata_ or {}
                domain = meta.get("domain", "")
                bucket = by_domain.setdefault(domain, []) if domain else uncategorized
                date_str = m.updated_at.strftime("%m-%d") if m.updated_at else ""
                bucket.append(f"[{date_str}] {m.content}")

            lines = [
                "# Session Briefing\n",
                f"**User**: {uid}",
                f"**Date**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"**Recent memories (last 7 days)**: {len(recent)} items\n",
            ]

            if domains:
                lines.append("## Active Domains")
                for name, info in domains.items():
                    count = len(by_domain.get(name, []))
                    if count:
                        lines.append(f"- **{info['display']}** ({name}): {count} recent memories")
                lines.append("")

            for domain, items in by_domain.items():
                if not domain:
                    continue
                display = domains.get(domain, {}).get("display", domain)
                lines.append(f"### {display}")
                for item in items[:8]:
                    lines.append(f"- {item}")
                if len(items) > 8:
                    lines.append(f"- ... and {len(items) - 8} more")
                lines.append("")

            if uncategorized:
                lines.append("### Uncategorized")
                for item in uncategorized[:5]:
                    lines.append(f"- {item}")
                if len(uncategorized) > 5:
                    lines.append(f"- ... and {len(uncategorized) - 5} more")
                lines.append("")

            lines.append(
                "Use this briefing as context. Ask me what I'd like to work on today."
            )
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.prompt(
        name="project-context",
        description="Load all memories for a specific project or domain. "
        "Pass the domain name (e.g. 'OSMP', 'mem0') to get full project context.",
    )
    async def project_context(domain: str) -> str:
        uid = user_id_var.get(None) or "arthaszeng"
        db = SessionLocal()
        try:
            from app.utils.db import get_user_and_app
            user, _ = get_user_and_app(db, user_id=uid, app_id="cursor")

            memories = (
                db.query(Memory)
                .filter(
                    Memory.user_id == user.id,
                    Memory.state == MemoryState.active,
                )
                .order_by(Memory.updated_at.desc())
                .all()
            )

            domain_lower = domain.lower()
            matched = []
            for m in memories:
                meta = m.metadata_ or {}
                mem_domain = (meta.get("domain") or "").lower()
                content_lower = (m.content or "").lower()
                if domain_lower in mem_domain or domain_lower in content_lower:
                    matched.append(m)

            categories: dict[str, list[str]] = {}
            for m in matched:
                meta = m.metadata_ or {}
                cats = meta.get("categories", ["uncategorized"])
                if isinstance(cats, str):
                    cats = [cats]
                for cat in cats:
                    categories.setdefault(cat, []).append(m.content)

            domains_info = get_domains()
            display = domain
            for name, info in domains_info.items():
                if domain_lower in name.lower() or domain_lower in [a.lower() for a in info.get("aliases", [])]:
                    display = info.get("display", name)
                    break

            lines = [
                f"# Project Context: {display}\n",
                f"**Total memories**: {len(matched)}\n",
            ]

            for cat, items in sorted(categories.items()):
                lines.append(f"## {cat.title()} ({len(items)})")
                for item in items[:10]:
                    lines.append(f"- {item}")
                if len(items) > 10:
                    lines.append(f"- ... and {len(items) - 10} more")
                lines.append("")

            if not matched:
                lines.append(f"No memories found for domain '{domain}'. Try a different name or alias.")

            lines.append(
                "Use this context to help with tasks related to this project."
            )
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.prompt(
        name="who-am-i",
        description="Show the user's profile: preferences, habits, personal info, "
        "and technical stack from stored memories.",
    )
    async def who_am_i() -> str:
        uid = user_id_var.get(None) or "arthaszeng"
        client = _get_memory_client_safe()
        if not client:
            return "Memory system unavailable."

        queries = [
            "personal preferences habits hobbies",
            "technical stack tools programming languages",
            "work job company role career",
        ]
        seen_ids = set()
        all_results: dict[str, list[str]] = {
            "Personal": [],
            "Tech & Tools": [],
            "Work & Career": [],
        }

        for query, label in zip(queries, all_results.keys()):
            hits = await asyncio.to_thread(
                _search_memories_sync, client, query, uid, 30
            )
            for h in hits:
                hid = str(h.id)
                if hid in seen_ids:
                    continue
                seen_ids.add(hid)
                payload = h.payload or {}
                text = payload.get("data", "")
                if text and h.score > 0.3:
                    all_results[label].append(text)

        lines = [f"# Profile: {uid}\n"]
        for label, items in all_results.items():
            if items:
                lines.append(f"## {label}")
                for item in items[:8]:
                    lines.append(f"- {item}")
                lines.append("")

        total = sum(len(v) for v in all_results.values())
        if total == 0:
            lines.append("No profile memories found yet. Start chatting to build your profile.")

        lines.append(
            "Use this profile to personalize responses. "
            "Do not repeat these facts back unless explicitly asked."
        )
        return "\n".join(lines)

    @mcp.prompt(
        name="review-memories",
        description="List memories that may need cleanup: uncategorized, "
        "possibly stale, or duplicated. Useful for memory hygiene.",
    )
    async def review_memories() -> str:
        uid = user_id_var.get(None) or "arthaszeng"
        db = SessionLocal()
        try:
            from app.utils.db import get_user_and_app
            user, _ = get_user_and_app(db, user_id=uid, app_id="cursor")

            all_active = (
                db.query(Memory)
                .filter(
                    Memory.user_id == user.id,
                    Memory.state == MemoryState.active,
                )
                .order_by(Memory.created_at.asc())
                .all()
            )

            uncategorized = []
            stale_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
            stale = []
            short = []

            for m in all_active:
                meta = m.metadata_ or {}
                if not meta.get("domain") and not meta.get("categories"):
                    uncategorized.append(m)
                updated = m.updated_at or m.created_at
                if updated and updated.replace(tzinfo=datetime.UTC) < stale_cutoff:
                    stale.append(m)
                if m.content and len(m.content) < 15:
                    short.append(m)

            lines = [
                "# Memory Review\n",
                f"**Total active memories**: {len(all_active)}\n",
            ]

            if uncategorized:
                lines.append(f"## Uncategorized ({len(uncategorized)})")
                lines.append("These memories have no domain or category metadata:")
                for m in uncategorized[:10]:
                    lines.append(f"- `{m.id}`: {m.content[:100]}")
                if len(uncategorized) > 10:
                    lines.append(f"- ... and {len(uncategorized) - 10} more")
                lines.append("")

            if short:
                lines.append(f"## Very Short ({len(short)})")
                lines.append("These might be too vague to be useful:")
                for m in short[:10]:
                    lines.append(f"- `{m.id}`: {m.content}")
                lines.append("")

            if stale:
                lines.append(f"## Stale ({len(stale)})")
                lines.append("Not updated in 30+ days — may be outdated:")
                for m in stale[:10]:
                    date = (m.updated_at or m.created_at).strftime("%Y-%m-%d") if (m.updated_at or m.created_at) else "?"
                    lines.append(f"- `{m.id}` [{date}]: {m.content[:80]}")
                if len(stale) > 10:
                    lines.append(f"- ... and {len(stale) - 10} more")
                lines.append("")

            if not uncategorized and not short and not stale:
                lines.append("All memories look healthy! No cleanup needed.")

            lines.append(
                "\nSuggest which memories to update, merge, or delete. "
                "Use the `delete_memories` tool with IDs to remove stale ones."
            )
            return "\n".join(lines)
        finally:
            db.close()

    @mcp.prompt(
        name="custom-instructions",
        description="Load the current custom instructions configured in OpenMemory. "
        "These guide how memories are extracted and classified.",
    )
    async def custom_instructions() -> str:
        db = SessionLocal()
        try:
            from app.models import Config as ConfigModel
            config = db.query(ConfigModel).filter(ConfigModel.key == "main").first()

            instructions = None
            if config and config.value:
                instructions = config.value.get("openmemory", {}).get("custom_instructions")

            from app.utils.prompts import build_fact_extraction_prompt, build_categorization_prompt

            lines = ["# OpenMemory Instructions\n"]

            if instructions:
                lines.append("## Custom Instructions (from config)")
                lines.append(instructions)
                lines.append("")

            lines.append("## Fact Extraction Prompt")
            lines.append("This is how memories are extracted from conversations:\n")
            lines.append(build_fact_extraction_prompt())
            lines.append("")

            lines.append("## Categorization Prompt")
            lines.append("This is how memories are classified into domains:\n")
            lines.append(build_categorization_prompt())

            return "\n".join(lines)
        finally:
            db.close()

    logger.info("Registered 6 MCP prompts: recall, briefing, project-context, who-am-i, review-memories, custom-instructions")
