import json
import logging
import os
from typing import List

import httpx
from app.utils.docker_host import get_docker_host_url
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT
from dotenv import load_dotenv

load_dotenv()

CATEGORIZATION_PROVIDER = os.getenv("CATEGORIZATION_PROVIDER", "ollama")
CATEGORIZATION_MODEL = os.getenv("CATEGORIZATION_MODEL", "qwen2.5:7b")

OLLAMA_JSON_INSTRUCTION = (
    "\nIMPORTANT: You MUST respond with ONLY a valid JSON object in this exact format: "
    '{\"categories\": [\"cat1\", \"cat2\"]}. No other text, no markdown, no explanation.'
)


def _get_ollama_base_url() -> str:
    """Resolve Ollama base URL using the same logic as mem0's LLM client."""
    explicit = os.getenv("CATEGORIZATION_OLLAMA_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    host = get_docker_host_url()
    return f"http://{host}:11434"


def _categorize_via_ollama(memory: str) -> List[str]:
    base_url = _get_ollama_base_url()
    url = f"{base_url}/api/chat"
    payload = {
        "model": CATEGORIZATION_MODEL,
        "messages": [
            {"role": "system", "content": MEMORY_CATEGORIZATION_PROMPT + OLLAMA_JSON_INSTRUCTION},
            {"role": "user", "content": memory},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": 128,
            "temperature": 0,
            "top_p": 0.9,
        },
    }
    logging.info(f"[Categorization] POST {url} model={CATEGORIZATION_MODEL}")
    resp = httpx.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    parsed = json.loads(content)
    categories = parsed.get("categories", [])
    if not isinstance(categories, list):
        return []
    return [str(c).strip().lower() for c in categories if c]


def _categorize_via_openai(memory: str) -> List[str]:
    from openai import OpenAI
    from pydantic import BaseModel

    class MemoryCategories(BaseModel):
        categories: List[str]

    client = OpenAI()
    completion = client.beta.chat.completions.parse(
        model=CATEGORIZATION_MODEL or "gpt-4o-mini",
        messages=[
            {"role": "system", "content": MEMORY_CATEGORIZATION_PROMPT},
            {"role": "user", "content": memory},
        ],
        response_format=MemoryCategories,
        temperature=0,
    )
    parsed: MemoryCategories = completion.choices[0].message.parsed
    return [cat.strip().lower() for cat in parsed.categories]


def get_categories_for_memory(memory: str) -> List[str]:
    try:
        if CATEGORIZATION_PROVIDER == "openai":
            return _categorize_via_openai(memory)
        return _categorize_via_ollama(memory)
    except Exception as e:
        logging.error(f"[Categorization] Failed (provider={CATEGORIZATION_PROVIDER}): {e}")
        return []
