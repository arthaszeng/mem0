"""Read authenticated user info from nginx gateway-injected headers.

The nginx gateway has already verified the token (JWT or API Key) via
auth_request and injected X-Auth-* headers. This module provides:
1. get_authenticated_user() — user identity from headers
2. resolve_project() — project lookup + role-based access check
"""

import datetime
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import App, Project, ProjectMember, ProjectRole, User

logger = logging.getLogger(__name__)

ROLE_LEVEL = {
    ProjectRole.read_only: 0,
    ProjectRole.read_write: 1,
    ProjectRole.admin: 2,
    ProjectRole.owner: 3,
}


class AuthenticatedUser:
    """Lightweight wrapper for the gateway-authenticated user identity."""

    def __init__(self, user_id: str, username: str, is_superadmin: bool, db_user: "User"):
        self.user_id = user_id
        self.username = username
        self.is_superadmin = is_superadmin
        self.db_user = db_user

    @property
    def id(self):
        return self.db_user.id


def _slugify(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ensure_default_project(db: Session, db_user: "User") -> None:
    """Create a personal default project for a user if none exists."""
    slug = _slugify(db_user.user_id)
    existing = db.query(Project).filter(Project.slug == slug).first()
    if existing:
        already_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == existing.id,
            ProjectMember.user_id == db_user.id,
        ).first()
        if not already_member:
            db.add(ProjectMember(
                project_id=existing.id,
                user_id=db_user.id,
                role=ProjectRole.owner,
            ))
        return

    project = Project(
        name=f"{db_user.user_id}",
        slug=slug,
        owner_id=db_user.id,
        description="Auto-created personal project",
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(
        project_id=project.id,
        user_id=db_user.id,
        role=ProjectRole.owner,
    ))
    logger.info("Created default project '%s' for user %s", slug, db_user.user_id)


def get_authenticated_user(request: Request, db: Session = Depends(get_db)) -> AuthenticatedUser:
    """FastAPI dependency: reads user from nginx-injected headers.
    Auto-provisions OpenMemory User on first access."""
    auth_user_id = request.headers.get("X-Auth-User-Id")
    auth_username = request.headers.get("X-Auth-Username", "")
    auth_is_superadmin = request.headers.get("X-Auth-Is-Superadmin", "false") == "true"

    if not auth_user_id:
        raise HTTPException(401, "Not authenticated via gateway")

    db_user = db.query(User).filter(User.user_id == auth_username).first()
    if not db_user:
        db_user = User(
            user_id=auth_username,
            name=auth_username,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        db.add(db_user)
        db.flush()

        default_app = App(name="openmemory", owner_id=db_user.id)
        db.add(default_app)

        _ensure_default_project(db, db_user)

        db.commit()
        db.refresh(db_user)
        logger.info("Auto-provisioned OpenMemory user: %s", auth_username)
    else:
        has_projects = db.query(ProjectMember).filter(
            ProjectMember.user_id == db_user.id,
        ).first()
        if not has_projects:
            _ensure_default_project(db, db_user)
            db.commit()
            logger.info("Created default project for existing user: %s", auth_username)

    return AuthenticatedUser(
        user_id=auth_user_id,
        username=auth_username,
        is_superadmin=auth_is_superadmin,
        db_user=db_user,
    )


class ProjectContext:
    """Resolved project with the user's role."""

    def __init__(self, project: Project, role: ProjectRole):
        self.project = project
        self.role = role

    @property
    def project_id(self):
        return self.project.id

    @property
    def slug(self):
        return self.project.slug


def resolve_project(
    auth: AuthenticatedUser,
    db: Session,
    project_slug: Optional[str],
    min_role: ProjectRole = ProjectRole.read_only,
) -> Optional[ProjectContext]:
    """Resolve project from slug and verify the user has at least min_role.
    Returns None if project_slug is None (backward compat for no-project queries)."""
    if not project_slug:
        return None

    project = db.query(Project).filter(Project.slug == project_slug).first()
    if not project:
        raise HTTPException(404, f"Project '{project_slug}' not found")

    if auth.is_superadmin:
        return ProjectContext(project, ProjectRole.owner)

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == auth.db_user.id,
    ).first()
    if not member:
        raise HTTPException(403, "Not a member of this project")

    if ROLE_LEVEL.get(member.role, 0) < ROLE_LEVEL.get(min_role, 0):
        raise HTTPException(403, f"Requires at least '{min_role.value}' role on project")

    return ProjectContext(project, member.role)
