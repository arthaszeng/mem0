"""Search result reranking using cross-encoder or external API.

Supports multiple backends:
- "cross-encoder": Uses sentence-transformers CrossEncoder locally (fallback)
- "jina": Uses Jina Reranker API
- "cohere": Uses Cohere Rerank API
- None/disabled: No reranking (default)

Configured via environment variables:
- RERANKER_PROVIDER: "jina" | "cohere" | "cross-encoder" | "" (disabled)
- RERANKER_API_KEY: API key for Jina or Cohere
- RERANKER_MODEL: Model name (optional, uses provider defaults)
"""

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

RERANKER_PROVIDER = (os.getenv("RERANKER_PROVIDER") or "").strip().lower()
RERANKER_API_KEY = os.getenv("RERANKER_API_KEY", "").strip()
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "").strip()
MEMORY_FILTER_ENABLED = os.getenv("MEMORY_FILTER_ENABLED", "false").lower() in ("true", "1", "yes")
MEMORY_FILTER_THRESHOLD = float(os.getenv("MEMORY_FILTER_THRESHOLD", "0.5"))


def rerank(query: str, results: list[dict], top_k: int) -> list[dict]:
    if not results:
        return results
    if not RERANKER_PROVIDER:
        return results[:top_k]

    try:
        if RERANKER_PROVIDER == "jina":
            return _rerank_jina(query, results, top_k)
        if RERANKER_PROVIDER == "cohere":
            return _rerank_cohere(query, results, top_k)
        if RERANKER_PROVIDER == "cross-encoder":
            return _rerank_cross_encoder(query, results, top_k)
    except Exception as e:
        logger.warning("Reranking failed (%s): %s", RERANKER_PROVIDER, e)
    return results[:top_k]


def _rerank_jina(query: str, results: list[dict], top_k: int) -> list[dict]:
    if not RERANKER_API_KEY:
        return results[:top_k]
    docs = [r.get("memory") or "" for r in results]
    payload = {
        "query": query,
        "documents": docs,
        "top_n": min(top_k, len(docs)),
        "return_documents": False,
    }
    if RERANKER_MODEL:
        payload["model"] = RERANKER_MODEL
    resp = httpx.post(
        "https://api.jina.ai/v1/rerank",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RERANKER_API_KEY}",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    ranked = []
    for item in data.get("results", []):
        idx = item.get("index", -1)
        score = item.get("relevance_score", 0.0)
        if 0 <= idx < len(results):
            r = dict(results[idx])
            r["score"] = score
            ranked.append(r)
    return ranked[:top_k]


def _rerank_cohere(query: str, results: list[dict], top_k: int) -> list[dict]:
    if not RERANKER_API_KEY:
        return results[:top_k]
    docs = [r.get("memory") or "" for r in results]
    payload = {
        "query": query,
        "documents": docs,
        "top_n": min(top_k, len(docs)),
    }
    if RERANKER_MODEL:
        payload["model"] = RERANKER_MODEL
    resp = httpx.post(
        "https://api.cohere.com/v2/rerank",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RERANKER_API_KEY}",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    ranked = []
    for item in data.get("results", []):
        idx = item.get("index", -1)
        score = item.get("relevance_score", 0.0)
        if 0 <= idx < len(results):
            r = dict(results[idx])
            r["score"] = score
            ranked.append(r)
    return ranked[:top_k]


def _rerank_cross_encoder(query: str, results: list[dict], top_k: int) -> list[dict]:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.warning("sentence-transformers not installed, skipping cross-encoder rerank")
        return results[:top_k]

    model_name = RERANKER_MODEL or "cross-encoder/ms-marco-MiniLM-L-6-v2"
    encoder = CrossEncoder(model_name)
    pairs = [(query, r.get("memory") or "") for r in results]
    scores = encoder.predict(pairs)
    scored = [(results[i], float(s)) for i, s in enumerate(scores)]
    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [dict(r) for r, s in scored[:top_k]]
    for i, r in enumerate(ranked):
        r["score"] = scored[i][1]
    return ranked


RELEVANCE_PROMPT = """Score each memory's relevance to the query from 0.0 (irrelevant) to 1.0 (highly relevant).
Return ONLY a JSON array of numbers in the same order as the memories, e.g. [0.9, 0.2, 0.7].
No explanation."""


async def filter_by_relevance(
    query: str, results: list[dict], threshold: float | None = None
) -> list[dict]:
    if not MEMORY_FILTER_ENABLED or not results:
        return results
    thresh = threshold if threshold is not None else MEMORY_FILTER_THRESHOLD
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return results

    try:
        from openai import AsyncOpenAI

        client_kwargs = {"api_key": api_key}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            client_kwargs["base_url"] = base_url
        client = AsyncOpenAI(**client_kwargs)

        texts = [r.get("memory") or "" for r in results]
        numbered = "\n".join(f"{i+1}. {t[:500]}" for i, t in enumerate(texts))
        prompt = f"Query: {query}\n\nMemories:\n{numbered}\n\n{RELEVANCE_PROMPT}"

        response = await client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )
        content = (response.choices[0].message.content or "").strip()
        scores = json.loads(content)
        if not isinstance(scores, list) or len(scores) != len(results):
            return results
        filtered = [
            results[i] for i in range(len(results))
            if i < len(scores) and float(scores[i]) >= thresh
        ]
        return filtered
    except Exception as e:
        logger.warning("LLM relevance filter failed: %s", e)
        return results
