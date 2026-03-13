from unittest.mock import MagicMock, patch

from tests.conftest import TEST_USERNAME


def test_search_memories_with_mock(client):
    """Test search endpoint with mocked memory client."""
    mock_client = MagicMock()
    mock_client.embedding_model.embed.return_value = [0.1] * 1536

    mock_point = MagicMock()
    mock_point.id = "test-id-123"
    mock_point.score = 0.95
    mock_point.payload = {
        "data": "Test memory content",
        "hash": "abc123",
        "created_at": "2026-01-01T00:00:00",
        "user_id": TEST_USERNAME,
    }

    mock_result = MagicMock()
    mock_result.points = [mock_point]
    mock_client.vector_store.client.query_points.return_value = mock_result
    mock_client.vector_store.collection_name = "openmemory"

    with patch("app.routers.memories.get_memory_client", return_value=mock_client):
        response = client.post(
            "/api/v1/memories/search",
            json={"query": "test query", "user_id": TEST_USERNAME},
        )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) >= 1
    assert data["results"][0]["memory"] == "Test memory content"


def test_search_memories_no_client(client):
    """Test search when memory client is unavailable."""
    with patch("app.routers.memories.get_memory_client", return_value=None):
        response = client.post(
            "/api/v1/memories/search",
            json={"query": "test query", "user_id": TEST_USERNAME},
        )
    assert response.status_code == 503
