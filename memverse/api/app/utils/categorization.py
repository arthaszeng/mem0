"""
Domain-aware memory categorization.

Pipeline:
  1. Fast keyword matching against DB-backed domain registry → deterministic domain
  2. LLM call for fine-grained categories + tags (domain hint injected)
  3. Return (domain, categories, tags) triple
  4. If LLM suggests an unknown domain, record it as a candidate for auto-discovery
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import httpx
from app.utils.docker_host import get_docker_host_url
from app.utils.domain_registry import get_domains, record_domain_candidate
from app.utils.prompts import (
    OLLAMA_CATEGORIZATION_SUFFIX,
    STANDARD_CATEGORIES_SET,
    build_categorization_prompt,
)
from dotenv import load_dotenv

load_dotenv()

CATEGORIZATION_PROVIDER = os.getenv("CATEGORIZATION_PROVIDER", "ollama")
_DEFAULT_MODELS = {"ollama": "qwen2.5:7b", "openai": "gpt-4o-mini"}
CATEGORIZATION_MODEL = os.getenv(
    "CATEGORIZATION_MODEL",
    _DEFAULT_MODELS.get(CATEGORIZATION_PROVIDER, "qwen2.5:7b"),
)


def _get_ollama_base_url() -> str:
    explicit = os.getenv("CATEGORIZATION_OLLAMA_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    host = get_docker_host_url()
    return f"http://{host}:11434"


# ---------------------------------------------------------------------------
# Pre-computed lowercase index for fast keyword matching
# ---------------------------------------------------------------------------
_lowered_cache: Optional[Dict[str, dict]] = None
_lowered_domains_id: Optional[int] = None


def _get_lowered_domains() -> Dict[str, dict]:
    """Return a lowercased index of aliases/keywords, rebuilt only when domains change."""
    global _lowered_cache, _lowered_domains_id
    domains = get_domains()
    cur_id = id(domains)
    if _lowered_cache is not None and _lowered_domains_id == cur_id:
        return _lowered_cache

    lowered: Dict[str, dict] = {}
    for domain_name, info in domains.items():
        lowered[domain_name] = {
            "aliases": [a.lower() for a in info.get("aliases", [])],
            "keywords": [k.lower() for k in info.get("keywords", [])],
        }
    _lowered_cache = lowered
    _lowered_domains_id = cur_id
    return _lowered_cache


# ---------------------------------------------------------------------------
# Keyword-based domain matching (fast, deterministic, no LLM needed)
# ---------------------------------------------------------------------------
def match_domain_by_keywords(text: str) -> Optional[str]:
    """Return the best-matching domain name, or None if no match.

    Uses bidirectional substring matching:
      - alias/keyword IN text  (e.g. "会议" found in long input)
      - text IN alias          (e.g. search query "event" is substring of "MyEvent")
    """
    text_lower = text.lower().strip()
    if not text_lower:
        return None

    lowered = _get_lowered_domains()
    scores: dict[str, int] = {}
    text_len = len(text_lower)

    for domain_name, idx in lowered.items():
        score = 0
        for a in idx["aliases"]:
            if a in text_lower or (text_len >= 3 and text_lower in a):
                score += 3
        for k in idx["keywords"]:
            if k in text_lower or (text_len >= 3 and text_lower in k):
                score += 1
        if score > 0:
            scores[domain_name] = score

    if not scores:
        return None
    return max(scores, key=scores.get)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Parse LLM output
# ---------------------------------------------------------------------------
def _parse_result(
    parsed: dict,
    keyword_domain: Optional[str],
    known_domains: Dict[str, dict],
    memory_snippet: str = "",
) -> Tuple[str, List[str], List[str]]:
    """Parse LLM JSON into (domain, categories, tags), with keyword fallback.

    Trust hierarchy:
      1. keyword match (deterministic, highest trust)
      2. LLM suggestion (probabilistic, may hallucinate)

    Key rule: if keyword matching found NO match but LLM assigns a
    known project domain, we REJECT the LLM assignment and treat it
    as "General" — the LLM is forced-picking from limited options.
    The LLM's raw suggestion is still recorded as a candidate for
    auto-discovery.
    """
    domain = parsed.get("domain", "")
    if isinstance(domain, str):
        domain = domain.strip()
    else:
        domain = ""

    llm_suggested_domain = domain

    if not domain or domain.lower() in ("", "general", "unknown"):
        # LLM gave nothing useful — use keyword match or "General"
        domain = keyword_domain or "General"

    elif keyword_domain and keyword_domain == domain:
        # Keyword and LLM agree — high confidence, keep it
        pass

    elif keyword_domain and keyword_domain != domain:
        # Keyword and LLM disagree — trust keyword (deterministic)
        if keyword_domain in known_domains:
            domain = keyword_domain

    elif keyword_domain is None and domain in known_domains:
        # CRITICAL FIX: keyword found NOTHING but LLM picked a known
        # project domain.  This is almost certainly a forced guess
        # (e.g., stock trading classified as OSMP because the LLM
        # has no better option).  Record as candidate and fall back.
        record_domain_candidate(llm_suggested_domain, memory_snippet)
        domain = "General"

    elif domain not in known_domains and domain not in ("Personal", "Work/Career", "General"):
        # LLM suggested a novel domain name — record for auto-discovery
        record_domain_candidate(llm_suggested_domain, memory_snippet)
        domain = keyword_domain or "General"

    raw_categories = parsed.get("categories", [])
    if isinstance(raw_categories, str):
        raw_categories = [c.strip() for c in raw_categories.split(",") if c.strip()]
    elif not isinstance(raw_categories, list):
        raw_categories = []
    categories = [str(c).strip().lower() for c in raw_categories if c]

    categories = [c for c in categories if c in STANDARD_CATEGORIES_SET]

    if not categories:
        categories.append("reference")

    tags = parsed.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if t]

    return domain, categories, tags


# ---------------------------------------------------------------------------
# LLM categorization
# ---------------------------------------------------------------------------
def _categorize_via_ollama(
    memory: str, keyword_domain: Optional[str], known_domains: Dict[str, dict]
) -> Tuple[str, List[str], List[str]]:
    base_url = _get_ollama_base_url()
    url = f"{base_url}/api/chat"

    hint = ""
    if keyword_domain:
        info = known_domains.get(keyword_domain, {})
        hint = f"\n\nHINT: This memory likely belongs to domain '{keyword_domain}' ({info.get('display', '')})."

    prompt = build_categorization_prompt() + OLLAMA_CATEGORIZATION_SUFFIX

    payload = {
        "model": CATEGORIZATION_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": memory + hint},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": 256,
            "temperature": 0,
            "top_p": 0.9,
        },
    }
    logging.info("[Categorization] POST %s model=%s", url, CATEGORIZATION_MODEL)
    resp = httpx.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    parsed = json.loads(content)
    return _parse_result(parsed, keyword_domain, known_domains, memory[:200])


def _categorize_via_openai(
    memory: str, keyword_domain: Optional[str], known_domains: Dict[str, dict]
) -> Tuple[str, List[str], List[str]]:
    from openai import OpenAI
    from pydantic import BaseModel

    class MemoryClassification(BaseModel):
        domain: str
        categories: List[str]
        tags: List[str]

    hint = ""
    if keyword_domain:
        info = known_domains.get(keyword_domain, {})
        hint = f"\n\nHINT: This memory likely belongs to domain '{keyword_domain}' ({info.get('display', '')})."

    prompt = build_categorization_prompt()

    client = OpenAI()
    completion = client.beta.chat.completions.parse(
        model=CATEGORIZATION_MODEL or "gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": memory + hint},
        ],
        response_format=MemoryClassification,
        temperature=0,
    )
    parsed_obj: MemoryClassification = completion.choices[0].message.parsed
    raw = {
        "domain": parsed_obj.domain,
        "categories": parsed_obj.categories,
        "tags": parsed_obj.tags,
    }
    return _parse_result(raw, keyword_domain, known_domains, memory[:200])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_categories_for_memory(memory: str) -> List[str]:
    """Legacy interface: returns only categories."""
    _, categories, _ = classify_memory(memory)
    return categories


def get_categories_and_tags_for_memory(memory: str) -> Tuple[List[str], List[str]]:
    """Legacy interface: returns (categories, tags)."""
    _, categories, tags = classify_memory(memory)
    return categories, tags


def classify_memory(memory: str) -> Tuple[str, List[str], List[str]]:
    """
    Full classification: returns (domain, categories, tags).

    1. Keyword matching for fast domain identification
    2. LLM for fine-grained categories + tags + domain confirmation
    """
    known_domains = get_domains()
    keyword_domain = match_domain_by_keywords(memory)

    try:
        if CATEGORIZATION_PROVIDER == "openai":
            return _categorize_via_openai(memory, keyword_domain, known_domains)
        return _categorize_via_ollama(memory, keyword_domain, known_domains)
    except Exception as e:
        logging.error(
            "[Categorization] LLM failed (provider=%s): %s",
            CATEGORIZATION_PROVIDER, e,
        )
        domain = keyword_domain or "General"
        categories = ["reference"]
        tags = re.findall(r"#(\w+)", memory)
        return domain, categories, tags
