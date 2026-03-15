"""Tests for v1.1 Entity Scoping features:
- run_id column on Memory model
- Graph-enhanced search integration
"""
import uuid
import datetime

from tests.conftest import TEST_USER_ID, TEST_APP_ID, TEST_PROJECT_ID


class TestRunIdColumn:
    def test_create_memory_with_run_id(self, db_session):
        from app.models import Memory, MemoryState
        mid = uuid.uuid4()
        db_session.add(Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Test run scoped memory",
            state=MemoryState.active,
            run_id="run-001",
        ))
        db_session.commit()

        mem = db_session.query(Memory).filter(Memory.id == mid).first()
        assert mem.run_id == "run-001"

    def test_create_memory_without_run_id(self, db_session):
        from app.models import Memory, MemoryState
        mid = uuid.uuid4()
        db_session.add(Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Unscoped memory", state=MemoryState.active,
        ))
        db_session.commit()

        mem = db_session.query(Memory).filter(Memory.id == mid).first()
        assert mem.run_id is None

    def test_filter_by_run_id(self, db_session):
        from app.models import Memory, MemoryState
        run = "session-abc"
        db_session.add(Memory(
            id=uuid.uuid4(), user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Session memory", state=MemoryState.active,
            run_id=run,
        ))
        db_session.commit()

        found = db_session.query(Memory).filter(Memory.run_id == run).all()
        assert len(found) == 1


class TestRegressions:
    def test_health(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
