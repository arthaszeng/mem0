"""
Domain-aware memory classification prompts.

All domain data is loaded from the DB-backed registry (domain_registry.py).
The KNOWN_DOMAINS variable is a lazy accessor that always returns the
current registry — no restart needed when domains change.
"""

from typing import Dict, List

from app.utils.domain_registry import get_domains


def _build_domain_summary_for_prompt(domains: Dict[str, dict]) -> str:
    """Generate a domain description block to inject into LLM prompts."""
    lines = []
    for domain_name, info in domains.items():
        aliases = ", ".join(info["aliases"][:6])
        kw_sample = ", ".join(info["keywords"][:10])
        lines.append(
            f"- {domain_name} ({info['display']}): "
            f"aliases=[{aliases}]; keywords=[{kw_sample}, ...]"
        )
    return "\n".join(lines)


STANDARD_CATEGORIES = [
    "architecture",
    "implementation",
    "requirement",
    "configuration",
    "bugfix",
    "decision",
    "learning",
    "workflow",
    "reference",
    "preference",
]

STANDARD_CATEGORIES_SET = frozenset(STANDARD_CATEGORIES)


def build_categorization_prompt() -> str:
    """Build the categorization prompt dynamically from current domains."""
    domains = get_domains()
    domain_block = _build_domain_summary_for_prompt(domains)
    domain_names = ", ".join(f'"{k}"' for k in domains.keys())

    return f"""You are a memory classifier. Given a piece of stored information ("memory"), determine:
1. **domain**: Which project/activity area this memory belongs to
2. **categories**: The type of knowledge this memory represents
3. **tags**: Keyword tags for search

## Known Domains
{domain_block}
- Personal: personal life, preferences, habits, family, pets
- Work/Career: job, company, team, career info unrelated to a specific project
- General: anything that doesn't fit a specific domain

## Knowledge-Type Categories (pick 1-3 from this EXACT list)
- architecture: system design, tech stack choices, deployment topology, infrastructure
- implementation: coding details, API endpoints, algorithms, specific code logic
- requirement: business rules, compliance rules, product specs, constraints
- configuration: env vars, deployment params, settings, connection strings
- bugfix: bug fixes, troubleshooting, root cause analysis, workarounds
- decision: technical decisions, trade-offs, why X was chosen over Y
- learning: lessons learned, new knowledge, tips, best practices discovered
- workflow: processes, approval flows, operational procedures, step-by-step guides
- reference: factual info, data assets, credentials, contact info, project status
- preference: personal preferences, habits, communication style, tool choices

## CRITICAL RULES
- **domain** must be ONE of: {domain_names}, "Personal", "Work/Career", or "General".
- Only assign a project domain if the memory CLEARLY contains that domain's aliases or keywords.
- If the memory does NOT contain any recognizable domain-specific terms, use "Work/Career" (for work topics) or "General" (for everything else). Do NOT force-assign a project domain just because it's the closest match.
- **categories** MUST only use values from the 10 categories listed above. Do NOT invent new categories.
- Categories describe the TYPE of knowledge, not the technical area (technical area is conveyed by domain and tags).
- **tags** should be 3-8 short keywords useful for search (technical terms, tool names, etc.).

## Output Format
Return ONLY this JSON:
{{"domain": "...", "categories": ["..."], "tags": ["..."]}}
"""


OLLAMA_CATEGORIZATION_SUFFIX = (
    "\nIMPORTANT: Respond with ONLY a valid JSON object with keys "
    '"domain", "categories", "tags". No markdown, no explanation.'
)


def build_fact_extraction_prompt() -> str:
    """Build the fact extraction prompt with domain context injection."""
    domains = get_domains()
    domain_block = _build_domain_summary_for_prompt(domains)
    domain_rules = []
    for name, info in domains.items():
        sample_terms = ", ".join(info["aliases"][:4] + info["keywords"][:4])
        domain_rules.append(
            f"- If input contains {sample_terms} terms → use [{info['display']}]"
        )
    rules_block = "\n".join(domain_rules)

    first_domain = next(iter(domains.values()), None)
    example_display = first_domain["display"] if first_domain else "项目域"

    return f"""You are a Knowledge Organizer. Extract factual information from input and store as distinct, searchable facts.

## CRITICAL: Domain Context Prefix
Every extracted fact MUST start with a domain context prefix in square brackets.
Determine which project/domain the input belongs to, then prepend it.

Known domains:
{domain_block}
- [Personal] for personal preferences, habits, biographical info
- [Work] for general work/career info

## Rules for Domain Prefix
{rules_block}
- If input has #hashtags, preserve them AFTER the domain prefix
- If unclear, infer from context clues

## Examples

Input: #OSMP #合规 拍照合规规则: 每场会至少6张照片
Output: {{"facts": ["[{example_display}] #OSMP #合规 拍照合规规则: 每场会至少6张照片"]}}

Input: 合规流涉及凌晨的拍照风险打标和E&C系统的同步
Output: {{"facts": ["[{example_display}] 合规流涉及凌晨的拍照风险打标和E&C系统的同步"]}}

Input: 我叫张三,在某科技公司做架构师
Output: {{"facts": ["[Work] 名字是张三,在某科技公司做架构师"]}}

Input: 我喜欢用Vim编辑器
Output: {{"facts": ["[Personal] 喜欢用Vim编辑器"]}}

Input: Hi
Output: {{"facts": []}}

## Output Rules
- Return ONLY valid JSON with key "facts" containing a list of strings.
- Each fact MUST start with [DomainName] prefix.
- After the prefix, preserve any #hashtags from input.
- Keep facts concise but information-dense.
- Detect input language and record facts in the same language.
- Do not fabricate information.

## SECURITY: Sensitive Data
- NEVER record actual passwords, API keys, tokens, secrets, credentials, or connection strings.
- If the input contains sensitive values, record the fact that the config EXISTS but replace the actual value with [REDACTED].
- Example: "DB password is p@ss123" → "[Work] 数据库密码已配置 [REDACTED]"
- Example: "API key: sk-abc123" → "[Work] API key 已配置 [REDACTED]"
"""
