"""Tests for v2.1.0 Project-Scoped Filtering:
- Cross-user import visible in same project
- Default project cannot be deleted
- Non-owner cannot delete project
- Project cascade delete
- User purge cascades to owned projects
- Auto-resolve to default project when no slug given
"""
import uuid
import datetime

from tests.conftest import (
    TEST_USER_ID, TEST_APP_ID, TEST_PROJECT_ID, TEST_PROJECT_SLUG, TEST_USERNAME,
    _TestSessionLocal,
)


def _make_user(db, username: str):
    from app.models import User
    uid = uuid.uuid4()
    user = User(id=uid, user_id=username, name=username.title())
    db.add(user)
    db.commit()
    return user


def _make_project(db, owner_id, slug: str, is_default: bool = False):
    from app.models import Project, ProjectMember, ProjectRole
    pid = uuid.uuid4()
    project = Project(id=pid, name=slug, slug=slug, owner_id=owner_id, is_default=is_default)
    db.add(project)
    db.commit()
    member = ProjectMember(project_id=pid, user_id=owner_id, role=ProjectRole.owner)
    db.add(member)
    db.commit()
    return project


def _make_memory(db, user_id, app_id, project_id, content: str = "test memory"):
    from app.models import Memory, MemoryState
    mid = uuid.uuid4()
    mem = Memory(
        id=mid, user_id=user_id, app_id=app_id, project_id=project_id,
        content=content, state=MemoryState.active,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(mem)
    db.commit()
    return mem


class TestImportCrossUserVisibleInSameProject:
    """After importing another user's memories into project C, they belong to project C."""

    def test_imported_memory_visible_via_project(self, db_session):
        from app.models import Memory, MemoryState

        other_user = _make_user(db_session, "other_user")
        mem = _make_memory(db_session, other_user.id, TEST_APP_ID, TEST_PROJECT_ID, "imported from other user")

        visible = (
            db_session.query(Memory)
            .filter(Memory.project_id == TEST_PROJECT_ID, Memory.state == MemoryState.active)
            .all()
        )
        assert any(str(m.id) == str(mem.id) for m in visible)

    def test_imported_memory_not_visible_via_user_id(self, db_session):
        from app.models import Memory, MemoryState

        other_user = _make_user(db_session, "other_user_2")
        mem = _make_memory(db_session, other_user.id, TEST_APP_ID, TEST_PROJECT_ID, "imported mem")

        user_memories = (
            db_session.query(Memory)
            .filter(Memory.user_id == TEST_USER_ID, Memory.state == MemoryState.active)
            .all()
        )
        assert not any(str(m.id) == str(mem.id) for m in user_memories)


class TestDefaultProjectProtection:
    def test_default_project_cannot_be_deleted(self, client):
        response = client.delete(f"/api/v1/projects/{TEST_PROJECT_SLUG}")
        assert response.status_code == 403
        assert "Default project" in response.json().get("detail", "")


class TestNonOwnerCannotDeleteProject:
    def test_non_owner_cannot_delete(self, db_session):
        from app.models import ProjectMember, ProjectRole

        owner = _make_user(db_session, "proj_owner")
        project = _make_project(db_session, owner.id, "team-project")

        reader = _make_user(db_session, "proj_reader")
        db_session.add(ProjectMember(
            project_id=project.id, user_id=reader.id, role=ProjectRole.read_only,
        ))
        db_session.commit()

        from app.routers.projects import _require_project_access
        from fastapi import HTTPException
        import pytest

        class FakeAuth:
            is_superadmin = False
            db_user = reader

        with pytest.raises(HTTPException) as exc_info:
            _require_project_access(db_session, project, FakeAuth(), ProjectRole.owner)
        assert exc_info.value.status_code == 403


class TestProjectCascadeDelete:
    def test_cascade_deletes_all_memories(self, db_session):
        from app.models import Memory, MemoryState

        owner = _make_user(db_session, "cascade_owner")
        project = _make_project(db_session, owner.id, "doomed-project")

        mem1 = _make_memory(db_session, owner.id, TEST_APP_ID, project.id, "cascade mem 1")
        mem2 = _make_memory(db_session, owner.id, TEST_APP_ID, project.id, "cascade mem 2")

        from app.routers.projects import _cascade_delete_project
        count = _cascade_delete_project(db_session, project)
        assert count == 2

        remaining = db_session.query(Memory).filter(Memory.project_id == project.id).all()
        assert len(remaining) == 0


class TestUserPurgeCascadesOwnedProjects:
    def test_purge_deletes_owned_projects_and_memories(self, db_session):
        from app.models import Memory, Project

        owner = _make_user(db_session, "purge_victim")
        proj = _make_project(db_session, owner.id, "victim-project")
        _make_memory(db_session, owner.id, TEST_APP_ID, proj.id, "purge me")

        from app.routers.projects import _cascade_delete_project
        _cascade_delete_project(db_session, proj)

        assert db_session.query(Memory).filter(Memory.project_id == proj.id).count() == 0
        assert db_session.query(Project).filter(Project.id == proj.id).first() is None


class TestAutoResolveDefaultProject:
    def test_resolve_project_required_without_slug(self, db_session):
        from app.utils.gateway_auth import resolve_project_required, ProjectContext

        class FakeAuth:
            is_superadmin = False
            db_user = db_session.query(
                __import__("app.models", fromlist=["User"]).User
            ).filter_by(id=TEST_USER_ID).first()

        pctx = resolve_project_required(FakeAuth(), db_session, None)
        assert isinstance(pctx, ProjectContext)
        assert str(pctx.project_id) == str(TEST_PROJECT_ID)

    def test_resolve_project_required_with_slug(self, db_session):
        from app.utils.gateway_auth import resolve_project_required, ProjectContext

        class FakeAuth:
            is_superadmin = False
            db_user = db_session.query(
                __import__("app.models", fromlist=["User"]).User
            ).filter_by(id=TEST_USER_ID).first()

        pctx = resolve_project_required(FakeAuth(), db_session, TEST_PROJECT_SLUG)
        assert isinstance(pctx, ProjectContext)
        assert pctx.slug == TEST_PROJECT_SLUG
