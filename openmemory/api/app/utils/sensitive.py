"""
Sensitive data detection and masking.

Two-phase pipeline:
  Phase 1 (keyword fast check): O(1) scan for sensitive keywords.
          If none found, still run definitive patterns (sk-, AKIA, PEM, URLs).
  Phase 2 (regex mask): precise pattern matching and value masking (~0.005ms).

Both phases combined add < 0.01ms per memory — negligible vs the 15-30s
LLM classification call.

Hook points:
  - Ingestion: MCP add_memories / REST create_memory (before mem0.add)
  - Pre-storage: categorize_memory_background (after fact extraction)
"""

import logging
import re
from typing import List, NamedTuple

logger = logging.getLogger(__name__)

_MASK = "***MASKED***"

# ---------------------------------------------------------------------------
# Phase 1: Keyword fast check
# ---------------------------------------------------------------------------
SENSITIVE_KEYWORDS = frozenset([
    "password", "passwd", "pwd",
    "secret", "secret_key", "secretkey",
    "token", "bearer", "auth_token",
    "apikey", "api_key", "api-key", "api key", "access_key", "accesskey",
    "credential", "credentials",
    "private_key", "private-key", "privatekey",
    "connection_string", "conn_str", "connectionstring",
    "encryption_key", "master_key",
    "client_secret", "client_id",
    "ssh_key", "rsa_key",
    "密码", "口令", "密钥", "秘钥", "令牌",
])


def _keyword_hit(text: str) -> bool:
    """Fast O(n) keyword scan. Returns True if any sensitive keyword found."""
    lower = text.lower()
    return any(kw in lower for kw in SENSITIVE_KEYWORDS)


# ---------------------------------------------------------------------------
# Phase 2: Regex patterns
#
# Two groups:
#   DEFINITIVE — always checked (format alone is proof of a secret)
#   KEYWORD_GATED — only checked when a keyword was found (avoid false
#                   positives on innocent "key = value" pairs)
# ---------------------------------------------------------------------------

_DEFINITIVE_PATTERNS: List[re.Pattern] = [
    # OpenAI / GitHub style keys: sk-..., pk-..., ghp-...
    re.compile(r'\b(sk|pk|ghp|gho|ghu|ghs|ghr)-[a-zA-Z0-9_\-]{16,}\b'),
    # AWS keys: AKIA...
    re.compile(r'\bAKIA[A-Z0-9]{12,}\b'),
    # Connection strings with embedded credentials: user:pass@host:port
    re.compile(r'\b[A-Za-z0-9._%+\-]+:[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+:\d+\b'),
    # DSN / JDBC / database URLs with embedded credentials
    re.compile(
        r'(?i)(mysql|postgres|postgresql|mongodb|redis|amqp|mssql)://'
        r'[A-Za-z0-9._%+\-]+:[A-Za-z0-9._%+\-]+@',
    ),
    # PEM private keys
    re.compile(r'-----BEGIN\s+(RSA\s+|EC\s+|DSA\s+)?PRIVATE\s+KEY-----'),
]

_KEYWORD_GATED_PATTERNS: List[re.Pattern] = [
    # password/secret/master_key = value
    re.compile(
        r'(?i)(password|passwd|pwd|secret|secret_key|master_key|encryption_key)'
        r'\s*[:=]\s*["\']?(\S+)["\']?',
    ),
    # api_key / access_key / client_secret = value
    re.compile(
        r'(?i)(api[_\- ]?key|apikey|access[_\-]?key|accesskey|client[_\-]?secret)'
        r'\s*[:=]\s*["\']?(\S+)["\']?',
    ),
    # token / bearer = value  OR  "bearer <value>" (auth header style)
    re.compile(
        r'(?i)(token|bearer)\s*[:=]?\s*["\']?([A-Za-z0-9_\-\.]{8,})["\']?',
    ),
    # credential / conn_str = value
    re.compile(
        r'(?i)(credential|credentials|connection[_\-]?string|conn[_\-]?str)'
        r'\s*[:=]\s*["\']?(.+?)["\']?(?=\s|$|,|;)',
    ),
    # Chinese patterns: 密码是: value / 密码: value / 密码=value
    re.compile(r'(密码|口令|密钥|秘钥|令牌)\s*[是为]?\s*[:：=]\s*(\S+)'),
]


class SensitiveMatch(NamedTuple):
    pattern_idx: int
    start: int
    end: int
    matched_text: str


def detect_sensitive(text: str) -> List[SensitiveMatch]:
    """Return all sensitive matches in the text."""
    matches = []
    keyword_hit = _keyword_hit(text)

    for i, pat in enumerate(_DEFINITIVE_PATTERNS):
        for m in pat.finditer(text):
            matches.append(SensitiveMatch(i, m.start(), m.end(), m.group()))

    if keyword_hit:
        offset = len(_DEFINITIVE_PATTERNS)
        for i, pat in enumerate(_KEYWORD_GATED_PATTERNS):
            for m in pat.finditer(text):
                matches.append(SensitiveMatch(offset + i, m.start(), m.end(), m.group()))

    return matches


def _mask_definitive(text: str) -> str:
    """Mask definitive patterns (always run)."""
    result = text

    for pat in _DEFINITIVE_PATTERNS:
        def _replace(m: re.Match) -> str:
            full = m.group(0)
            if full.startswith(("sk-", "pk-", "ghp-", "gho-", "ghu-", "ghs-", "ghr-")):
                return f"{full[:3]}{_MASK}"
            if full.startswith("AKIA"):
                return f"AKIA{_MASK}"
            if "-----BEGIN" in full:
                return f"-----BEGIN PRIVATE KEY----- {_MASK}"
            if "://" in full:
                parts = full.split("://", 1)
                at_idx = parts[1].find("@") if len(parts) > 1 else -1
                after_at = parts[1][at_idx:] if at_idx >= 0 else ""
                return f"{parts[0]}://{_MASK}{after_at}"
            # user:pass@host:port
            at_idx = full.find("@")
            if at_idx >= 0:
                return f"{_MASK}{full[at_idx:]}"
            return _MASK
        result = pat.sub(_replace, result)

    return result


def _mask_keyword_gated(text: str) -> str:
    """Mask keyword-gated patterns (run only when keyword detected)."""
    result = text

    for pat in _KEYWORD_GATED_PATTERNS:
        def _replace(m: re.Match) -> str:
            groups = m.groups()
            if len(groups) >= 2:
                key = groups[0]
                return f"{key} = {_MASK}"
            return _MASK
        result = pat.sub(_replace, result)

    return result


def mask_sensitive(text: str) -> str:
    """Full regex masking — apply all relevant patterns."""
    result = _mask_definitive(text)
    if _keyword_hit(text):
        result = _mask_keyword_gated(result)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def sanitize_text(text: str) -> str:
    """Full sanitization pipeline: keyword check → regex mask.

    Returns the original text if no sensitive content detected,
    or masked text otherwise.
    """
    masked = mask_sensitive(text)
    if masked != text:
        logger.info(
            "[Sensitive] Masked sensitive content in %d-char input",
            len(text),
        )
    return masked


def has_sensitive_content(text: str) -> bool:
    """Check if text contains sensitive data (without masking)."""
    return len(detect_sensitive(text)) > 0
