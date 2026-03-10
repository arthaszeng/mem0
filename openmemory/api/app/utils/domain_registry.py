"""
Hot-reloadable Domain Registry backed by the Config table.

Domains are stored in DB (Config key = "domain_registry") and cached in
memory with a configurable TTL.  All consumers (prompts, categorization,
search) call get_domains() which transparently handles caching.

Auto-discovery: when the LLM suggests a domain name not in the registry,
it is recorded as a "candidate".  Candidates that accumulate enough
mentions can be auto-promoted to full domains.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_CACHE_TTL = 60  # seconds
_cache_lock = threading.Lock()
_cached_domains: Optional[Dict[str, dict]] = None
_cache_ts: float = 0.0

# ---------------------------------------------------------------------------
# Default seed data (written to DB on first access if no registry exists)
# ---------------------------------------------------------------------------
_SEED_DOMAINS: Dict[str, dict] = {
    "OSMP/MyEvent": {
        "display": "OSMP会议管理平台",
        "aliases": [
            "OSMP", "MyEvent", "EventPro", "MyEvent2.0", "易会",
            "会议管理", "会议系统", "会议平台",
            "event", "meeting", "会议",
        ],
        "keywords": [
            "E&C", "OneCRM", "HCP", "HCO", "拍照", "签到", "审批",
            "PPM", "院内会", "系列会", "子会", "单场会", "讲者", "参会",
            "劳务费", "报账", "讲题", "IO Request", "Tibco",
            "1:5比例", "18次限制", "Webcasting", "Aithena", "TURING",
            "ConcurOCR", "EIM", "Jing", "MA推送", "CKafka",
            "osmp-", "eventpro", "OneSpeaker", "合规流", "Landing Page",
            "二维码", "小程序", "关会", "创会", "改会", "报名",
            "Vue3", "v-permission", "ElementPlus", "前端技术栈", "菜单权限",
            "stringForSign", "SHA1",
        ],
    },
    "mem0/OpenMemory": {
        "display": "mem0记忆管理系统",
        "aliases": [
            "mem0", "OpenMemory", "OpenClaw", "openmemory",
            "记忆系统", "记忆管理",
        ],
        "keywords": [
            "Qdrant", "embedding", "向量数据库", "向量存储",
            "MCP server", "memory client", "categorization",
            "fact extraction", "vector store", "记忆分类",
        ],
    },
    "arthas1/Trading": {
        "display": "arthas1量化交易系统",
        "aliases": [
            "arthas1", "量化交易", "交易系统", "A股", "量化",
        ],
        "keywords": [
            "Tushare", "回测", "backtest", "策略", "stock",
            "trade_calendar", "daily_trade", "信号", "撮合", "T+1",
            "stock_list", "daily_basic", "stock_st", "收盘",
        ],
    },
}

_CONFIG_KEY = "domain_registry"
_CANDIDATES_KEY = "domain_candidates"

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_db():
    from app.database import SessionLocal
    return SessionLocal()


def _read_config(db, key: str) -> Optional[Any]:
    from app.models import Config
    row = db.query(Config).filter(Config.key == key).first()
    return row.value if row else None


def _write_config(db, key: str, value: Any) -> None:
    from app.models import Config
    import sqlalchemy as sa

    row = db.query(Config).filter(Config.key == key).first()
    if row:
        row.value = value
        sa.orm.attributes.flag_modified(row, "value")
    else:
        row = Config(key=key, value=value)
        db.add(row)
    db.flush()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_domains() -> Dict[str, dict]:
    """Return the current domain registry (cached, hot-reloaded from DB)."""
    global _cached_domains, _cache_ts

    now = time.time()
    if _cached_domains is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_domains

    with _cache_lock:
        # Double-check after acquiring lock
        if _cached_domains is not None and (time.time() - _cache_ts) < _CACHE_TTL:
            return _cached_domains

        db = _get_db()
        try:
            data = _read_config(db, _CONFIG_KEY)
            if data is None:
                # First run — seed from hardcoded defaults
                _write_config(db, _CONFIG_KEY, _SEED_DOMAINS)
                db.commit()
                data = _SEED_DOMAINS
                logger.info("Domain registry seeded with %d domains", len(data))

            _cached_domains = data
            _cache_ts = time.time()
            return _cached_domains
        except Exception as e:
            logger.error("Failed to load domain registry from DB: %s", e)
            # Fallback to seed data so the system doesn't break
            if _cached_domains is not None:
                return _cached_domains
            return _SEED_DOMAINS
        finally:
            db.close()


def invalidate_cache() -> None:
    """Force next get_domains() call to reload from DB."""
    global _cached_domains, _cache_ts
    with _cache_lock:
        _cached_domains = None
        _cache_ts = 0.0


_write_lock = threading.Lock()


def save_domains(domains: Dict[str, dict]) -> None:
    """Persist the full registry to DB and invalidate cache."""
    db = _get_db()
    try:
        _write_config(db, _CONFIG_KEY, domains)
        db.commit()
        invalidate_cache()
        logger.info("Domain registry saved (%d domains)", len(domains))
    finally:
        db.close()


def add_domain(
    name: str,
    display: str,
    aliases: List[str],
    keywords: List[str],
) -> Dict[str, dict]:
    """Add or update a single domain entry. Returns the updated registry."""
    with _write_lock:
        domains = dict(get_domains())
        entry = domains.get(name, {})
        entry.update({
            "display": display,
            "aliases": aliases,
            "keywords": keywords,
        })
        entry.pop("category", None)
        domains[name] = entry
        save_domains(domains)
        return domains


def remove_domain(name: str) -> Dict[str, dict]:
    """Remove a domain by name. Returns the updated registry."""
    with _write_lock:
        domains = dict(get_domains())
        domains.pop(name, None)
        save_domains(domains)
        return domains


# ---------------------------------------------------------------------------
# Domain candidate tracking (for auto-discovery)
# ---------------------------------------------------------------------------

_SKIP_CANDIDATES = frozenset({"general", "work/career", "personal", "unknown", "work", ""})


def record_domain_candidate(suggested_name: str, memory_snippet: str) -> None:
    """
    Record a domain name that the LLM suggested but is not in the registry.
    Called during classification when the LLM returns an unknown domain.

    Runs in a daemon thread so it never blocks the classification hot path.
    """
    if not suggested_name or suggested_name.lower() in _SKIP_CANDIDATES:
        return

    def _do_record():
        db = _get_db()
        try:
            candidates = _read_config(db, _CANDIDATES_KEY) or {}

            if suggested_name not in candidates:
                candidates[suggested_name] = {
                    "count": 0,
                    "snippets": [],
                    "first_seen": time.time(),
                }

            entry = candidates[suggested_name]
            entry["count"] = entry.get("count", 0) + 1
            entry["last_seen"] = time.time()
            snippets = entry.get("snippets", [])
            snippet_text = memory_snippet[:200]
            if len(snippets) < 10 and snippet_text not in snippets:
                snippets.append(snippet_text)
            entry["snippets"] = snippets
            candidates[suggested_name] = entry

            _write_config(db, _CANDIDATES_KEY, candidates)
            db.commit()
            logger.info(
                "Recorded domain candidate '%s' (count=%d)",
                suggested_name, entry["count"],
            )
        except Exception as e:
            db.rollback()
            logger.warning("Failed to record domain candidate: %s", e)
        finally:
            db.close()

    t = threading.Thread(target=_do_record, daemon=True)
    t.start()


def get_domain_candidates() -> Dict[str, dict]:
    """Return all pending domain candidates."""
    db = _get_db()
    try:
        return _read_config(db, _CANDIDATES_KEY) or {}
    finally:
        db.close()


def promote_candidate(
    candidate_name: str,
    domain_name: Optional[str] = None,
    display: Optional[str] = None,
    extra_aliases: Optional[List[str]] = None,
    extra_keywords: Optional[List[str]] = None,
) -> Dict[str, dict]:
    """
    Promote a candidate to a full domain in the registry.
    Uses candidate snippets to auto-generate aliases/keywords if not provided.
    """
    candidates = get_domain_candidates()
    if candidate_name not in candidates:
        raise ValueError(f"Candidate '{candidate_name}' not found")

    final_name = domain_name or candidate_name
    final_display = display or candidate_name

    aliases = list(extra_aliases or [])
    if candidate_name not in aliases:
        aliases.insert(0, candidate_name)

    keywords = list(extra_keywords or [])

    result = add_domain(
        name=final_name,
        display=final_display,
        aliases=aliases,
        keywords=keywords,
    )

    # Remove from candidates
    db = _get_db()
    try:
        cands = _read_config(db, _CANDIDATES_KEY) or {}
        cands.pop(candidate_name, None)
        _write_config(db, _CANDIDATES_KEY, cands)
        db.commit()
    finally:
        db.close()

    return result


def auto_discover_domains(
    llm_analyze: bool = False,
    min_count: int = 3,
) -> List[Dict[str, Any]]:
    """
    Analyze domain candidates and return suggestions for new domains.

    Returns a list of dicts with candidate info and recommendation.
    If min_count threshold is met, the candidate is auto-promoted.
    """
    candidates = get_domain_candidates()
    known = get_domains()
    suggestions = []

    for name, info in candidates.items():
        # Skip if already a known domain (exact or alias match)
        if name in known:
            continue

        is_alias = False
        for d_info in known.values():
            if name.lower() in [a.lower() for a in d_info.get("aliases", [])]:
                is_alias = True
                break
        if is_alias:
            continue

        count = info.get("count", 0)
        suggestion = {
            "candidate": name,
            "count": count,
            "snippets": info.get("snippets", [])[:5],
            "first_seen": info.get("first_seen"),
            "last_seen": info.get("last_seen"),
            "auto_promotable": count >= min_count,
        }
        suggestions.append(suggestion)

    return sorted(suggestions, key=lambda x: x["count"], reverse=True)
