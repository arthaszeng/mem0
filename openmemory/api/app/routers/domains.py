"""
Domain Registry management API.

Provides CRUD for the domain registry and domain auto-discovery.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.utils.domain_registry import (
    add_domain,
    auto_discover_domains,
    get_domain_candidates,
    get_domains,
    invalidate_cache,
    promote_candidate,
    remove_domain,
    save_domains,
)

router = APIRouter(prefix="/api/v1/domains", tags=["domains"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class DomainEntry(BaseModel):
    display: str
    aliases: List[str]
    keywords: List[str]
    category: Optional[str] = None


class AddDomainRequest(BaseModel):
    name: str
    display: str
    aliases: List[str]
    keywords: List[str]
    category: Optional[str] = None


class PromoteCandidateRequest(BaseModel):
    candidate_name: str
    domain_name: Optional[str] = None
    display: Optional[str] = None
    extra_aliases: Optional[List[str]] = None
    extra_keywords: Optional[List[str]] = None


class LLMAnalyzeRequest(BaseModel):
    """Request body for LLM-powered domain analysis on uncategorized memories."""
    min_memories: int = 5
    max_results: int = 10


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("/")
async def list_domains() -> Dict[str, Any]:
    """List all registered domains."""
    domains = get_domains()
    return {
        "count": len(domains),
        "domains": domains,
    }


@router.post("/")
async def create_or_update_domain(req: AddDomainRequest) -> Dict[str, Any]:
    """Add a new domain or update an existing one."""
    result = add_domain(
        name=req.name,
        display=req.display,
        aliases=req.aliases,
        keywords=req.keywords,
        category=req.category,
    )
    return {"message": f"Domain '{req.name}' saved", "count": len(result)}


class DeleteDomainRequest(BaseModel):
    name: str


@router.delete("/")
async def delete_domain(req: DeleteDomainRequest) -> Dict[str, Any]:
    """Remove a domain from the registry."""
    domains = get_domains()
    if req.name not in domains:
        raise HTTPException(status_code=404, detail=f"Domain '{req.name}' not found")
    result = remove_domain(req.name)
    return {"message": f"Domain '{req.name}' removed", "count": len(result)}


@router.post("/reload")
async def reload_domains() -> Dict[str, Any]:
    """Force reload the domain cache from DB."""
    invalidate_cache()
    domains = get_domains()
    return {"message": "Cache invalidated and reloaded", "count": len(domains)}


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------
@router.get("/candidates")
async def list_candidates() -> Dict[str, Any]:
    """List all domain candidates suggested by the LLM."""
    candidates = get_domain_candidates()
    return {
        "count": len(candidates),
        "candidates": candidates,
    }


@router.post("/candidates/promote")
async def promote(req: PromoteCandidateRequest) -> Dict[str, Any]:
    """Promote a candidate to a full domain."""
    try:
        result = promote_candidate(
            candidate_name=req.candidate_name,
            domain_name=req.domain_name,
            display=req.display,
            extra_aliases=req.extra_aliases,
            extra_keywords=req.extra_keywords,
        )
        return {"message": f"Candidate '{req.candidate_name}' promoted", "count": len(result)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/discover")
async def discover() -> Dict[str, Any]:
    """Analyze candidates and return auto-discovery suggestions."""
    suggestions = auto_discover_domains()
    return {
        "count": len(suggestions),
        "suggestions": suggestions,
    }


@router.post("/discover/analyze")
async def analyze_uncategorized(req: LLMAnalyzeRequest) -> Dict[str, Any]:
    """
    Use LLM to analyze memories classified as 'General' or 'Work/Career'
    and propose new domain groupings.
    """
    from app.database import SessionLocal
    from app.models import Memory, MemoryState

    db = SessionLocal()
    try:
        general_memories = (
            db.query(Memory)
            .filter(
                Memory.state == MemoryState.active,
                Memory.metadata_.op("->>")("domain").in_(
                    ["General", "Work/Career", "Work", None]
                ),
            )
            .limit(200)
            .all()
        )

        if len(general_memories) < req.min_memories:
            return {
                "message": f"Only {len(general_memories)} uncategorized memories found (min={req.min_memories})",
                "suggestions": [],
            }

        memory_texts = [m.content[:200] for m in general_memories]

        from app.utils.categorization import _get_ollama_base_url, CATEGORIZATION_MODEL
        import httpx
        import json

        prompt = f"""Analyze the following {len(memory_texts)} memory snippets and identify common themes/projects that could become named domains.

For each suggested domain, provide:
- name: a short identifier (like "ProjectX/Feature")
- display: Chinese display name
- aliases: list of name variants
- keywords: distinctive terms from the memories

Return JSON array of suggestions. Only suggest domains that have 3+ related memories.

Memories:
""" + "\n".join(f"- {t}" for t in memory_texts[:50])

        base_url = _get_ollama_base_url()
        resp = httpx.post(
            f"{base_url}/api/chat",
            json={
                "model": CATEGORIZATION_MODEL,
                "messages": [
                    {"role": "system", "content": "You analyze text and suggest domain groupings. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"num_predict": 1024, "temperature": 0.3},
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        result = json.loads(content)

        suggestions = result if isinstance(result, list) else result.get("suggestions", result.get("domains", []))

        return {
            "analyzed_memories": len(memory_texts),
            "suggestions": suggestions[:req.max_results],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")
    finally:
        db.close()
