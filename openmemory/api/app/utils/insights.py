"""Memory Insights — LLM-powered analysis of stored memories.

Generates user profile summaries, topic trends, and knowledge coverage.
"""
import asyncio
import logging
import os
from collections import Counter
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_PROFILE_PROMPT = """Based on the following memories stored by a user, generate a brief profile summary.
Include: main interests, expertise areas, work context, and notable patterns.
Keep it to 3-5 sentences.

Memories:
{memories}
"""


async def generate_user_profile(memories: list[dict]) -> dict | None:
    """Generate a concise user profile summary from memories using LLM."""
    if not memories:
        return {"summary": "No memories to analyze.", "generated_at": datetime.now(UTC).isoformat()}

    contents = []
    for m in memories[:100]:
        content = m.get("content", m.get("memory", ""))
        if content:
            contents.append(content[:500])
    if not contents:
        return {"summary": "No memory content to analyze.", "generated_at": datetime.now(UTC).isoformat()}

    formatted = "\n".join(f"- {c}" for c in contents)

    try:
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        client_kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        def _call():
            return client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "user", "content": _PROFILE_PROMPT.format(memories=formatted)},
                ],
                temperature=0.3,
                max_tokens=400,
            )

        response = await asyncio.to_thread(_call)
        summary = response.choices[0].message.content.strip()
        return {"summary": summary, "generated_at": datetime.now(UTC).isoformat()}
    except Exception as e:
        logger.warning("User profile generation failed: %s", e)
        return None


def compute_topic_trends(memories: list[dict], days: int = 30) -> list[dict]:
    """Analyze category/domain frequency changes over time."""
    now = datetime.now(UTC)
    recent_cutoff = now - timedelta(days=7)
    previous_cutoff = now - timedelta(days=days)

    recent_topics: Counter = Counter()
    previous_topics: Counter = Counter()

    for m in memories:
        created = m.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        elif not isinstance(created, datetime):
            continue

        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)

        topics = []
        for cat in m.get("categories", []) or []:
            name = cat if isinstance(cat, str) else cat.get("name", "")
            if name:
                topics.append(name)
        domain = m.get("metadata", {}).get("domain") or m.get("metadata_", {}).get("domain")
        if domain:
            topics.append(domain)

        if not topics:
            continue

        if recent_cutoff <= created <= now:
            for t in topics:
                recent_topics[t] += 1
        elif previous_cutoff <= created < recent_cutoff:
            for t in topics:
                previous_topics[t] += 1

    all_topics = set(recent_topics) | set(previous_topics)
    result = []
    for topic in all_topics:
        recent_count = recent_topics.get(topic, 0)
        previous_count = previous_topics.get(topic, 0)
        if recent_count > previous_count:
            trend = "rising"
        elif recent_count < previous_count:
            trend = "declining"
        else:
            trend = "stable"
        result.append({
            "topic": topic,
            "trend": trend,
            "recent_count": recent_count,
            "previous_count": previous_count,
        })
    result.sort(key=lambda x: x["recent_count"] + x["previous_count"], reverse=True)
    return result


def compute_knowledge_coverage(categories: list[dict], domains: list[dict], total_memories: int = 0) -> dict:
    """Analyze which domains/categories have rich vs sparse coverage."""
    if total_memories <= 0:
        total_memories = sum(c.get("count", 0) for c in categories) or 1
    total = total_memories
    if total == 0:
        return {
            "total_categories": len(categories),
            "total_domains": len(domains),
            "top_categories": [],
            "sparse_categories": [],
            "domain_coverage": [],
        }

    cat_with_pct = []
    for c in categories:
        count = c.get("count", 0)
        pct = round(100 * count / total, 1) if total else 0
        cat_with_pct.append({"name": c.get("name", ""), "count": count, "pct": pct})

    cat_with_pct.sort(key=lambda x: x["count"], reverse=True)
    top_categories = cat_with_pct[:10]
    sparse_categories = [c for c in cat_with_pct if c["count"] <= 2][:10]

    domain_with_pct = []
    for d in domains:
        count = d.get("count", 0)
        pct = round(100 * count / total, 1) if total else 0
        domain_with_pct.append({"name": d.get("name", ""), "count": count, "pct": pct})

    domain_with_pct.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_categories": len(categories),
        "total_domains": len(domains),
        "top_categories": top_categories,
        "sparse_categories": sparse_categories,
        "domain_coverage": domain_with_pct,
    }
