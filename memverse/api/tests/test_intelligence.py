"""Tests for v1.3 Intelligence features:
- Memory consolidation (prompt + similarity detection)
- Contradiction detection (prompt structure)
"""
import os
from unittest.mock import patch
from difflib import SequenceMatcher


class TestConsolidationPrompt:
    def test_prompt_exists(self):
        from app.utils.intelligence import CONSOLIDATION_PROMPT
        assert "consolidation" in CONSOLIDATION_PROMPT.lower()
        assert "merge" in CONSOLIDATION_PROMPT.lower()

    def test_consolidate_no_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            from app.utils.intelligence import consolidate_memories
            result = consolidate_memories([
                {"id": "1", "content": "memory one"},
                {"id": "2", "content": "memory two"},
            ])
            assert result == ""

    def test_consolidate_single_memory(self):
        from app.utils.intelligence import consolidate_memories
        result = consolidate_memories([{"id": "1", "content": "only memory"}])
        assert result == "only memory"


class TestContradictionPrompt:
    def test_prompt_exists(self):
        from app.utils.intelligence import CONTRADICTION_PROMPT
        assert "contradiction" in CONTRADICTION_PROMPT.lower()
        assert "{existing}" in CONTRADICTION_PROMPT
        assert "{new_memory}" in CONTRADICTION_PROMPT

    def test_detect_no_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            from app.utils.intelligence import detect_contradiction
            result = detect_contradiction("new fact", [{"id": "1", "content": "old fact"}])
            assert result["has_contradiction"] is False

    def test_detect_empty_existing(self):
        from app.utils.intelligence import detect_contradiction
        result = detect_contradiction("anything", [])
        assert result["has_contradiction"] is False


class TestSimilarityDetection:
    def test_similar_memories_detected(self):
        m1 = "Arthas uses Qdrant for vector storage in Memverse"
        m2 = "Arthas uses Qdrant for vector search in Memverse"
        ratio = SequenceMatcher(None, m1.lower(), m2.lower()).ratio()
        assert ratio > 0.6

    def test_dissimilar_memories_not_detected(self):
        m1 = "Arthas uses Qdrant for vector storage"
        m2 = "The weather is nice today in Shanghai"
        ratio = SequenceMatcher(None, m1.lower(), m2.lower()).ratio()
        assert ratio < 0.6


class TestRegressions:
    def test_health(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
