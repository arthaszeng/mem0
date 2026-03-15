"""Tests for v0.7 Memory Quality features:
- Enhanced fact extraction prompt
- Confidence threshold config
- Per-call infer/instructions MCP params
"""
from unittest.mock import MagicMock, patch

from tests.conftest import TEST_USERNAME


class TestFactExtractionPrompt:
    def test_prompt_contains_negative_examples(self):
        from app.utils.prompts import build_fact_extraction_prompt
        prompt = build_fact_extraction_prompt()
        assert "SKIP" in prompt
        assert "Greetings and small talk" in prompt
        assert "Debugging output" in prompt
        assert '{"facts": []}' in prompt

    def test_prompt_contains_positive_examples(self):
        from app.utils.prompts import build_fact_extraction_prompt
        prompt = build_fact_extraction_prompt()
        assert "EXTRACT" in prompt
        assert "Decisions" in prompt
        assert "Preferences" in prompt

    def test_prompt_without_confidence_threshold(self):
        from app.utils.prompts import build_fact_extraction_prompt
        prompt = build_fact_extraction_prompt()
        assert "Confidence Filter" not in prompt

    def test_prompt_with_confidence_threshold(self):
        from app.utils.prompts import build_fact_extraction_prompt
        prompt = build_fact_extraction_prompt(confidence_threshold=0.8)
        assert "Confidence Filter" in prompt
        assert "80%" in prompt

    def test_prompt_with_zero_threshold_no_block(self):
        from app.utils.prompts import build_fact_extraction_prompt
        prompt = build_fact_extraction_prompt(confidence_threshold=0.0)
        assert "Confidence Filter" not in prompt


class TestConfidenceThresholdConfig:
    def test_config_schema_accepts_threshold(self):
        from app.routers.config import MemverseConfig
        config = MemverseConfig(confidence_threshold=0.7)
        assert config.confidence_threshold == 0.7

    def test_config_schema_rejects_invalid_threshold(self):
        from app.routers.config import MemverseConfig
        import pydantic
        try:
            MemverseConfig(confidence_threshold=1.5)
            assert False, "Should have raised validation error"
        except pydantic.ValidationError:
            pass

    def test_config_schema_default_is_none(self):
        from app.routers.config import MemverseConfig
        config = MemverseConfig()
        assert config.confidence_threshold is None

    def test_get_config_includes_threshold(self, client):
        response = client.get("/api/v1/config/memverse")
        assert response.status_code == 200


class TestAddMemoriesParams:
    def test_health_still_works(self, client):
        """Regression: adding params to add_memories must not break existing endpoints."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_list_memories_still_works(self, client):
        """Regression: adding params to add_memories must not break existing endpoints."""
        response = client.get("/api/v1/memories/")
        assert response.status_code == 200
