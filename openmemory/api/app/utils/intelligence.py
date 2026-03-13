"""Intelligence utilities: memory consolidation and contradiction detection.

These are LLM-powered features that make the memory system smarter:
- Consolidation: merge near-duplicate memories into concise summaries
- Contradiction detection: detect when new memories conflict with existing ones
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

CONSOLIDATION_PROMPT = """You are a memory consolidation assistant. Given a list of similar memories, merge them into ONE concise memory that preserves all unique information.

Rules:
- Combine overlapping facts into a single statement
- Keep the most recent/specific details when duplicates exist
- Preserve all distinct pieces of information
- Output should be a single paragraph, max 2-3 sentences
- Return ONLY the consolidated text, no explanation

Memories to consolidate:
"""

CONTRADICTION_PROMPT = """You are a contradiction detector. Compare a NEW memory against EXISTING memories and determine if there is a direct contradiction.

A contradiction exists when:
- The new memory directly opposes or invalidates an existing memory
- Facts are mutually exclusive (e.g., "uses PostgreSQL" vs "uses SQLite")
- Preferences changed (e.g., "prefers dark mode" vs "prefers light mode")

NOT a contradiction:
- Additional information that supplements existing memories
- Different aspects of the same topic
- Unrelated memories

Return ONLY valid JSON:
{"has_contradiction": true/false, "contradicted_memory_id": "..." or null, "explanation": "..."}

EXISTING MEMORIES:
{existing}

NEW MEMORY:
{new_memory}
"""


def consolidate_memories(memories: list[dict]) -> str:
    """Merge similar memories into one consolidated text.

    Args:
        memories: List of {"id": "...", "content": "..."} dicts
    Returns:
        Consolidated text string, or empty string on failure.
    """
    if len(memories) <= 1:
        return memories[0]["content"] if memories else ""

    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return ""

        client_kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        memory_text = "\n".join(f"- {m['content']}" for m in memories)
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": CONSOLIDATION_PROMPT},
                {"role": "user", "content": memory_text},
            ],
            temperature=0,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Consolidation failed: %s", e)
        return ""


def detect_contradiction(new_memory: str, existing_memories: list[dict]) -> dict:
    """Check if a new memory contradicts any existing memories.

    Args:
        new_memory: The new memory content string.
        existing_memories: List of {"id": "...", "content": "..."} dicts to check against.
    Returns:
        {"has_contradiction": bool, "contradicted_memory_id": str|None, "explanation": str}
    """
    if not existing_memories:
        return {"has_contradiction": False, "contradicted_memory_id": None, "explanation": ""}

    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {"has_contradiction": False, "contradicted_memory_id": None, "explanation": "no API key"}

        client_kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        existing_text = "\n".join(f"[{m['id']}] {m['content']}" for m in existing_memories[:20])
        prompt = CONTRADICTION_PROMPT.replace("{existing}", existing_text).replace("{new_memory}", new_memory)

        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": prompt},
            ],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error("Contradiction detection failed: %s", e)
        return {"has_contradiction": False, "contradicted_memory_id": None, "explanation": str(e)}
