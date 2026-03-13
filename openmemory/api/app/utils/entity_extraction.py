"""LLM-based entity and relationship extraction from memory content.

Uses the configured OpenAI-compatible LLM to extract entities (people, projects,
technologies, places) and their relationships from memory text.
"""
import json
import logging
import os

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


def extract_entities(text: str) -> dict:
    """Extract entities and relations from text using LLM.

    Returns: {"entities": [...], "relations": [...]}
    """
    try:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        if not api_key:
            logger.debug("No OPENAI_API_KEY, skipping entity extraction")
            return {"entities": [], "relations": []}

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        entities = result.get("entities", [])
        relations = result.get("relations", [])

        for e in entities:
            if "name" not in e or "type" not in e:
                continue
            e["name"] = e["name"].strip().lower()

        return {"entities": entities, "relations": relations}

    except Exception as e:
        logger.error("Entity extraction failed: %s", e)
        return {"entities": [], "relations": []}
