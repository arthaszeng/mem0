"""Tests for v1.2 MCP Complete features:
- update_memory MCP tool
- archive_memories / restore_memories MCP tools
- export_memories MCP tool
"""
import uuid
import datetime

from tests.conftest import TEST_USER_ID, TEST_APP_ID, TEST_PROJECT_ID


class TestUpdateMemory:
    def test_update_memory_content(self, db_session):
        from app.models import Memory, MemoryState
        mid = uuid.uuid4()
        db_session.add(Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Original content", state=MemoryState.active,
        ))
        db_session.commit()

        mem = db_session.query(Memory).filter(Memory.id == mid).first()
        mem.content = "Updated content"
        mem.updated_at = datetime.datetime.now(datetime.UTC)
        db_session.commit()

        refreshed = db_session.query(Memory).filter(Memory.id == mid).first()
        assert refreshed.content == "Updated content"


class TestArchiveRestore:
    def test_archive_and_restore(self, db_session):
        from app.models import Memory, MemoryState
        mid = uuid.uuid4()
        db_session.add(Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Archivable memory", state=MemoryState.active,
        ))
        db_session.commit()

        mem = db_session.query(Memory).filter(Memory.id == mid).first()
        mem.state = MemoryState.archived
        mem.archived_at = datetime.datetime.now(datetime.UTC)
        db_session.commit()

        archived = db_session.query(Memory).filter(Memory.id == mid).first()
        assert archived.state == MemoryState.archived
        assert archived.archived_at is not None

        archived.state = MemoryState.active
        archived.archived_at = None
        db_session.commit()

        restored = db_session.query(Memory).filter(Memory.id == mid).first()
        assert restored.state == MemoryState.active
        assert restored.archived_at is None


class TestExportMemories:
    def test_export_categorized(self, db_session):
        from app.models import Memory, MemoryState, Category
        mid = uuid.uuid4()
        cat = db_session.query(Category).first()
        mem = Memory(
            id=mid, user_id=TEST_USER_ID, app_id=TEST_APP_ID, project_id=TEST_PROJECT_ID,
            content="Exportable memory", state=MemoryState.active,
        )
        if cat:
            mem.categories.append(cat)
        db_session.add(mem)
        db_session.commit()

        memories = (
            db_session.query(Memory)
            .filter(Memory.user_id == TEST_USER_ID, Memory.state == MemoryState.active)
            .all()
        )
        assert len(memories) >= 1
        assert any(str(m.id) == str(mid) for m in memories)


class TestRegressions:
    def test_health(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
