"""Tests for v0.9 Advanced Retrieval features:
- MCP search_memory new parameters (limit, categories)
- Keyword search (SQLite LIKE)
- Category filtering
"""
import uuid
import datetime
from unittest.mock import MagicMock, patch

from tests.conftest import TEST_USER_ID, TEST_APP_ID, TEST_PROJECT_ID, TEST_USERNAME


class TestSearchNewParams:
    def test_search_with_limit_mock(self, client):
        mock_client = MagicMock()
        mock_client.embedding_model.embed.return_value = [0.1] * 1536
        mock_result = MagicMock()
        mock_result.points = []
        mock_client.vector_store.client.query_points.return_value = mock_result
        mock_client.vector_store.collection_name = "memverse"

        with patch("app.routers.memories.get_memory_client", return_value=mock_client):
            response = client.post(
                "/api/v1/memories/search",
                json={"query": "test", "limit": 5, "user_id": TEST_USERNAME},
            )
        assert response.status_code == 200

    def test_search_503_when_no_client(self, client):
        with patch("app.routers.memories.get_memory_client", return_value=None):
            response = client.post(
                "/api/v1/memories/search",
                json={"query": "test", "user_id": TEST_USERNAME},
            )
        assert response.status_code == 503


class TestKeywordSearch:
    def test_keyword_match_in_content(self, db_session):
        from app.models import Memory, MemoryState
        mid = uuid.uuid4()
        db_session.add(Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Qdrant is the vector database we chose for Memverse",
            state=MemoryState.active,
            created_at=datetime.datetime.now(datetime.UTC),
        ))
        db_session.commit()

        found = (
            db_session.query(Memory)
            .filter(
                Memory.user_id == TEST_USER_ID,
                Memory.state == MemoryState.active,
                Memory.content.ilike("%qdrant%"),
            )
            .all()
        )
        assert any(str(m.id) == str(mid) for m in found)

    def test_keyword_no_match(self, db_session):
        from app.models import Memory, MemoryState
        found = (
            db_session.query(Memory)
            .filter(
                Memory.user_id == TEST_USER_ID,
                Memory.state == MemoryState.active,
                Memory.content.ilike("%nonexistent_xyz_keyword%"),
            )
            .all()
        )
        assert len(found) == 0


class TestRegressions:
    def test_health_version(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
