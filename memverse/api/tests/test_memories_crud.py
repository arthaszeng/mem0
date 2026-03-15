import uuid
from datetime import datetime, UTC

from tests.conftest import TEST_USER_ID, TEST_APP_ID, TEST_USERNAME


def _create_test_memory(db_session, content="Test memory content"):
    from app.models import Memory, MemoryState

    memory_id = uuid.uuid4()
    memory = Memory(
        id=memory_id,
        user_id=TEST_USER_ID,
        app_id=TEST_APP_ID,
        content=content,
        state=MemoryState.active,
        created_at=datetime.now(UTC),
    )
    db_session.add(memory)
    db_session.commit()
    return memory_id


def test_list_memories(client):
    response = client.get("/api/v1/memories/")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_get_memory_detail(client, db_session):
    memory_id = _create_test_memory(db_session, "Detail test memory")
    response = client.get(f"/api/v1/memories/{memory_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "Detail test memory"


def test_update_memory(client, db_session):
    memory_id = _create_test_memory(db_session, "Before update")
    response = client.put(
        f"/api/v1/memories/{memory_id}",
        json={"memory_content": "After update", "user_id": TEST_USERNAME},
    )
    assert response.status_code == 200


def test_get_nonexistent_memory(client):
    fake_id = uuid.uuid4()
    response = client.get(f"/api/v1/memories/{fake_id}")
    assert response.status_code == 404


def test_get_categories(client):
    response = client.get("/api/v1/memories/categories")
    assert response.status_code == 200
