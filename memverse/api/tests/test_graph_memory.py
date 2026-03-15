"""Tests for v1.0 Graph Memory features:
- Entity extraction (unit test with mock)
- Graph store operations (Kuzu)
- MCP tools for graph search
"""
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock


class TestEntityExtractionPrompt:
    def test_extraction_prompt_exists(self):
        from app.utils.entity_extraction import ENTITY_EXTRACTION_PROMPT
        assert "entities" in ENTITY_EXTRACTION_PROMPT
        assert "relations" in ENTITY_EXTRACTION_PROMPT
        assert "person" in ENTITY_EXTRACTION_PROMPT
        assert "technology" in ENTITY_EXTRACTION_PROMPT

    def test_extract_entities_no_api_key(self):
        """Without OPENAI_API_KEY, should return empty results gracefully."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            from app.utils.entity_extraction import extract_entities
            result = extract_entities("Arthas uses Qdrant for vector search")
            assert result == {"entities": [], "relations": []}


class TestGraphStore:
    def test_kuzu_init_and_add(self):
        tmpdir = tempfile.mkdtemp()
        try:
            import app.utils.graph_store as gs
            old_path = gs.GRAPH_DB_PATH
            old_db = gs._db
            old_conn = gs._conn
            gs.GRAPH_DB_PATH = os.path.join(tmpdir, "test_graph")
            gs._db = None
            gs._conn = None

            gs.add_entities(
                [{"name": "qdrant", "type": "technology"}, {"name": "arthas", "type": "person"}],
                [{"source": "arthas", "target": "qdrant", "relation": "uses"}],
                "test-mem-001",
            )

            entities = gs.list_entities(limit=10)
            assert len(entities) >= 2
            names = {e["name"] for e in entities}
            assert "qdrant" in names
            assert "arthas" in names

            results = gs.search_entities("qdrant")
            assert len(results) >= 1
            assert results[0]["name"] == "qdrant"

            results = gs.search_entities("nonexistent_xyz")
            assert len(results) == 0

            gs.GRAPH_DB_PATH = old_path
            gs._db = old_db
            gs._conn = old_conn
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestRegressions:
    def test_health(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
