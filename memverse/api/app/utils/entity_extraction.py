"""LLM-based entity and relationship extraction from memory content.

Uses the configured OpenAI-compatible LLM to extract entities (people, projects,
technologies, places) and their relationships from memory text.
Supports both single-memory and batch extraction.
"""
import json
import logging
import os
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

ENTITY_EXTRACTION_PROMPT = """Extract entities and relationships from the following memory text.

## Entity Types
- person: people, names, roles
- project: project names, product names
- technology: programming languages, frameworks, tools, databases, services
- organization: companies, teams, departments
- concept: architectural patterns, methodologies, standards
- place: cities, offices, regions

## Output Format
Return ONLY valid JSON:
{"entities": [{"name": "...", "type": "..."}], "relations": [{"source": "...", "target": "...", "relation": "..."}]}

Rules:
- Entity names should be normalized (lowercase, canonical form)
- Relations should be concise verbs/phrases: "uses", "works_at", "depends_on", "part_of", "created_by"
- If no entities found, return {"entities": [], "relations": []}
- Do NOT fabricate entities not present in the text
"""

BATCH_ENTITY_EXTRACTION_PROMPT = """Extract entities and relationships from EACH numbered memory below.

## Entity Types
- person: people, names, roles
- project: project names, product names
- technology: programming languages, frameworks, tools, databases, services
- organization: companies, teams, departments
- concept: architectural patterns, methodologies, standards
- place: cities, offices, regions

## Output Format
Return ONLY valid JSON — a dict keyed by memory number (as string):
{"1": {"entities": [...], "relations": [...]}, "2": {"entities": [...], "relations": [...]}, ...}

Each value has the same structure: {"entities": [{"name": "...", "type": "..."}], "relations": [{"source": "...", "target": "...", "relation": "..."}]}

Rules:
- Entity names should be normalized (lowercase, canonical form)
- Relations should be concise verbs/phrases: "uses", "works_at", "depends_on", "part_of", "created_by"
- If a memory has no entities, use {"entities": [], "relations": []}
- Do NOT fabricate entities not present in the text
- You MUST return an entry for every memory number provided
"""

ENTITY_BATCH_SIZE = 20
ENTITY_TIMEOUT = 120


def _get_client():
    """Return (OpenAI client, model) or (None, None) if unconfigured."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None
    kwargs = {"api_key": api_key}
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs), os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def _normalize_entities(result: dict) -> dict:
    for e in result.get("entities", []):
        if "name" in e:
            e["name"] = e["name"].strip().lower()
    return result


def extract_entities(text: str) -> dict:
    """Extract entities and relations from a single text using LLM."""
    try:
        client, model = _get_client()
        if not client:
            logger.debug("No OPENAI_API_KEY, skipping entity extraction")
            return {"entities": [], "relations": []}

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        return _normalize_entities(result)

    except Exception as e:
        logger.error("Entity extraction failed: %s", e)
        return {"entities": [], "relations": []}


def extract_entities_batch(
    items: List[Tuple[str, str]],
    batch_size: int = ENTITY_BATCH_SIZE,
) -> Dict[str, dict]:
    """Batch-extract entities from multiple memories in fewer LLM calls.

    Args:
        items: list of (memory_id, content) tuples
        batch_size: how many memories per LLM call (default 20)

    Returns:
        dict mapping memory_id -> {"entities": [...], "relations": [...]}
    """
    client, model = _get_client()
    if not client:
        logger.debug("No OPENAI_API_KEY, skipping batch entity extraction")
        return {}

    timed_client = client.with_options(timeout=ENTITY_TIMEOUT)
    all_results: Dict[str, dict] = {}
    total_batches = (len(items) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(items), batch_size):
        batch = items[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        numbered_texts = []
        idx_to_id = {}
        for i, (mid, content) in enumerate(batch, 1):
            numbered_texts.append(f"[{i}] {content}")
            idx_to_id[str(i)] = mid

        user_content = "\n\n".join(numbered_texts)

        try:
            logger.info(
                "Entity batch %d/%d (%d items)",
                batch_num, total_batches, len(batch),
            )
            response = timed_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": BATCH_ENTITY_EXTRACTION_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            batch_result = json.loads(response.choices[0].message.content)

            for idx_str, mid in idx_to_id.items():
                entry = batch_result.get(idx_str, {"entities": [], "relations": []})
                all_results[mid] = _normalize_entities(entry)

        except Exception as e:
            logger.warning("Entity batch %d/%d failed: %s", batch_num, total_batches, e)
            for mid in idx_to_id.values():
                all_results[mid] = {"entities": [], "relations": []}

    return all_results
