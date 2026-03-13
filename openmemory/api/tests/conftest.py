import pytest
import uuid
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models import User, App

TEST_USER_ID = uuid.uuid4()
TEST_APP_ID = uuid.uuid4()
TEST_USERNAME = "test_user"

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_test_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


Base.metadata.create_all(bind=_test_engine)
_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)

_seed_done = False


def _ensure_seed():
    global _seed_done
    if _seed_done:
        return
    session = _TestSessionLocal()
    try:
        user = User(id=TEST_USER_ID, user_id=TEST_USERNAME, name="Test User")
        session.add(user)
        app = App(id=TEST_APP_ID, name="test_client", owner_id=TEST_USER_ID, is_active=True)
        session.add(app)
        session.commit()
        _seed_done = True
    except Exception:
        session.rollback()
        _seed_done = True
    finally:
        session.close()


_ensure_seed()


@pytest.fixture()
def db_session():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


class FakeAuthUser:
    def __init__(self, db_user):
        self.user_id = TEST_USERNAME
        self.username = TEST_USERNAME
        self.is_superadmin = False
        self.db_user = db_user

    @property
    def id(self):
        return self.db_user.id


@pytest.fixture()
def client():
    from main import app
    from app.utils.gateway_auth import get_authenticated_user

    def override_get_db():
        session = _TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_auth():
        session = _TestSessionLocal()
        user = session.query(User).filter(User.id == TEST_USER_ID).first()
        return FakeAuthUser(user)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_authenticated_user] = override_auth

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
