"""Project CRUD and member management."""

import re
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models import Project, ProjectMember, ProjectRole, User
from app.utils.gateway_auth import AuthenticatedUser, get_authenticated_user
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddMemberRequest(BaseModel):
    username: str
    role: str = "normal"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _get_project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _get_member_role(db: Session, project_id: UUID, user_id: UUID) -> Optional[ProjectRole]:
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
    ).first()
    return member.role if member else None


def _require_project_access(
    db: Session, project: Project, user: AuthenticatedUser, min_role: ProjectRole = ProjectRole.read,
) -> ProjectRole:
    """Verify user has at least min_role on the project. Superadmins always pass."""
    if user.is_superadmin:
        return ProjectRole.admin
    role = _get_member_role(db, project.id, user.db_user.id)
    if role is None:
        raise HTTPException(403, "Not a member of this project")
    role_hierarchy = {ProjectRole.read: 0, ProjectRole.normal: 1, ProjectRole.admin: 2}
    if role_hierarchy.get(role, 0) < role_hierarchy.get(min_role, 0):
        raise HTTPException(403, f"Requires at least {min_role.value} role")
    return role


@router.post("")
def create_project(
    body: CreateProjectRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    slug = body.slug or _slugify(body.name)
    if db.query(Project).filter(Project.slug == slug).first():
        raise HTTPException(409, f"Project slug '{slug}' already exists")

    project = Project(
        name=body.name,
        slug=slug,
        owner_id=auth.db_user.id,
        description=body.description,
    )
    db.add(project)
    db.flush()

    member = ProjectMember(
        project_id=project.id,
        user_id=auth.db_user.id,
        role=ProjectRole.admin,
    )
    db.add(member)
    db.commit()
    db.refresh(project)

    return _project_dict(project, ProjectRole.admin)


@router.get("")
def list_projects(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if auth.is_superadmin:
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
    else:
        projects = (
            db.query(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == auth.db_user.id)
            .order_by(Project.created_at.desc())
            .all()
        )
    result = []
    for p in projects:
        role = _get_member_role(db, p.id, auth.db_user.id)
        result.append(_project_dict(p, role or ProjectRole.admin if auth.is_superadmin else role))
    return result


@router.get("/{slug}")
def get_project(
    slug: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    role = _require_project_access(db, project, auth)
    return _project_dict(project, role)


@router.put("/{slug}")
def update_project(
    slug: str,
    body: UpdateProjectRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    db.commit()
    db.refresh(project)
    role = _get_member_role(db, project.id, auth.db_user.id)
    return _project_dict(project, role or ProjectRole.admin)


@router.delete("/{slug}")
def delete_project(
    slug: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)
    db.delete(project)
    db.commit()
    return {"message": f"Project '{slug}' deleted"}


@router.get("/{slug}/members")
def list_members(
    slug: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all()
    return [
        {
            "id": str(m.id),
            "user_id": str(m.user_id),
            "username": m.user.user_id if m.user else None,
            "role": m.role.value,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in members
    ]


@router.post("/{slug}/members")
def add_member(
    slug: str,
    body: AddMemberRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    target_user = db.query(User).filter(User.user_id == body.username).first()
    if not target_user:
        raise HTTPException(404, f"User '{body.username}' not found")

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == target_user.id,
    ).first()
    if existing:
        raise HTTPException(409, "User already a member")

    try:
        role = ProjectRole(body.role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {body.role}")

    member = ProjectMember(project_id=project.id, user_id=target_user.id, role=role)
    db.add(member)
    db.commit()
    return {"message": f"Added {body.username} as {role.value}"}


@router.delete("/{slug}/members/{username}")
def remove_member(
    slug: str,
    username: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    target_user = db.query(User).filter(User.user_id == username).first()
    if not target_user:
        raise HTTPException(404, "User not found")

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project.id,
        ProjectMember.user_id == target_user.id,
    ).first()
    if not member:
        raise HTTPException(404, "Member not found")

    db.delete(member)
    db.commit()
    return {"message": f"Removed {username} from project"}


def _project_dict(project: Project, role: Optional[ProjectRole]) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "owner_id": str(project.owner_id),
        "my_role": role.value if role else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
