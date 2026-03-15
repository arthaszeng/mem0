"""Tests for v0.8 Memory Lifecycle features:
- expires_at column and TTL cleanup
- MemoryState.expired
"""
import uuid
import datetime

from tests.conftest import TEST_USER_ID, TEST_APP_ID


class TestExpiredState:
    def test_expired_state_exists(self):
        from app.models import MemoryState
        assert MemoryState.expired.value == "expired"


class TestExpiresAtColumn:
    def test_create_memory_with_expires(self, db_session):
        from app.models import Memory, MemoryState
        expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=24)
        memory = Memory(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            app_id=TEST_APP_ID,
            content="Session memory with TTL",
            state=MemoryState.active,
            expires_at=expires,
        )
        db_session.add(memory)
        db_session.commit()
        db_session.refresh(memory)
        assert memory.expires_at is not None

    def test_create_memory_without_expires(self, db_session):
        from app.models import Memory, MemoryState
        memory = Memory(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            app_id=TEST_APP_ID,
            content="Permanent memory",
            state=MemoryState.active,
        )
        db_session.add(memory)
        db_session.commit()
        db_session.refresh(memory)
        assert memory.expires_at is None


class TestTTLCleanup:
    def test_expire_stale_memories(self, db_session):
        from app.models import Memory, MemoryState
        from app.utils.ttl_cleanup import _expire_stale_memories

        past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=24)

        stale_id = uuid.uuid4()
        fresh_id = uuid.uuid4()

        db_session.add(Memory(
            id=stale_id, user_id=TEST_USER_ID, app_id=TEST_APP_ID,
            content="Should expire", state=MemoryState.active, expires_at=past,
        ))
        db_session.add(Memory(
            id=fresh_id, user_id=TEST_USER_ID, app_id=TEST_APP_ID,
            content="Should stay", state=MemoryState.active, expires_at=future,
        ))
        db_session.commit()

        count = _expire_stale_memories(session=db_session)
        assert count >= 1

        db_session.expire_all()
        stale = db_session.query(Memory).filter(Memory.id == stale_id).first()
        fresh = db_session.query(Memory).filter(Memory.id == fresh_id).first()
        assert stale.state == MemoryState.expired
        assert fresh.state == MemoryState.active


class TestRegressions:
    def test_health_endpoint(self, client):
        from app.version import __version__
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["version"] == __version__

    def test_list_memories(self, client):
        r = client.get("/api/v1/memories/")
        assert r.status_code == 200
