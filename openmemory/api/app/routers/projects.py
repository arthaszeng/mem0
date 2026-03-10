"""Project CRUD, member management, and invite system."""

import datetime
import re
import secrets
from typing import List, Optional
from uuid import UUID


def _utcnow() -> datetime.datetime:
    """Timezone-naive UTC now, consistent with SQLite storage."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

from app.database import get_db
from app.models import InviteStatus, Project, ProjectInvite, ProjectMember, ProjectRole, User
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
    role: str = "read_write"


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


ROLE_HIERARCHY = {
    ProjectRole.read_only: 0,
    ProjectRole.read_write: 1,
    ProjectRole.admin: 2,
    ProjectRole.owner: 3,
}


def _require_project_access(
    db: Session, project: Project, user: AuthenticatedUser, min_role: ProjectRole = ProjectRole.read_only,
) -> ProjectRole:
    """Verify user has at least min_role on the project. Superadmins always pass."""
    if user.is_superadmin:
        return ProjectRole.owner
    role = _get_member_role(db, project.id, user.db_user.id)
    if role is None:
        raise HTTPException(403, "Not a member of this project")
    if ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 0):
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
        role=ProjectRole.owner,
    )
    db.add(member)
    db.commit()
    db.refresh(project)

    return _project_dict(project, ProjectRole.owner)


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
        result.append(_project_dict(p, role or ProjectRole.owner if auth.is_superadmin else role))
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
    return _project_dict(project, role or ProjectRole.owner)


@router.delete("/{slug}")
def delete_project(
    slug: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    from app.models import Memory, MemoryState, memory_categories
    from app.utils.memory import get_memory_client
    import logging

    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    memories = db.query(Memory).filter(Memory.project_id == project.id).all()
    memory_ids = [m.id for m in memories]

    if memory_ids:
        try:
            memory_client = get_memory_client()
            if memory_client:
                for mid in memory_ids:
                    try:
                        memory_client.delete(str(mid))
                    except Exception as e:
                        logging.warning("Failed to delete memory %s from Qdrant: %s", mid, e)
        except Exception as e:
            logging.warning("Could not initialize memory client for cascade delete: %s", e)

        db.execute(memory_categories.delete().where(memory_categories.c.memory_id.in_(memory_ids)))
        for mem in memories:
            mem.state = MemoryState.deleted
            mem.deleted_at = _utcnow()

    db.query(ProjectInvite).filter(ProjectInvite.project_id == project.id).delete()
    db.query(ProjectMember).filter(ProjectMember.project_id == project.id).delete()

    for mem in memories:
        db.delete(mem)

    db.delete(project)
    db.commit()
    return {
        "message": f"Project '{slug}' deleted",
        "deleted_memories": len(memory_ids),
    }


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


class CreateInviteRequest(BaseModel):
    role: str = "read_write"
    expires_in_days: Optional[int] = 7


class RevokeInviteRequest(BaseModel):
    token: str


@router.post("/{slug}/invites")
def create_invite(
    slug: str,
    body: CreateInviteRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    try:
        role = ProjectRole(body.role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {body.role}")

    if role == ProjectRole.owner:
        raise HTTPException(400, "Cannot create invite with owner role")

    token = secrets.token_urlsafe(32)
    expires_at = None
    if body.expires_in_days:
        expires_at = _utcnow() + datetime.timedelta(days=body.expires_in_days)

    invite = ProjectInvite(
        project_id=project.id,
        token=token,
        role=role,
        created_by_id=auth.db_user.id,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return _invite_dict(invite)


@router.get("/{slug}/invites")
def list_invites(
    slug: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    invites = (
        db.query(ProjectInvite)
        .filter(ProjectInvite.project_id == project.id)
        .order_by(ProjectInvite.created_at.desc())
        .all()
    )
    return [_invite_dict(inv) for inv in invites]


@router.post("/{slug}/invites/revoke")
def revoke_invite(
    slug: str,
    body: RevokeInviteRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(db, slug)
    _require_project_access(db, project, auth, ProjectRole.admin)

    invite = db.query(ProjectInvite).filter(
        ProjectInvite.project_id == project.id,
        ProjectInvite.token == body.token,
    ).first()
    if not invite:
        raise HTTPException(404, "Invite not found")
    if invite.status != InviteStatus.pending:
        raise HTTPException(400, f"Invite already {invite.status.value}")

    invite.status = InviteStatus.revoked
    db.commit()
    return {"message": "Invite revoked"}


@router.get("/invites/{token}/info")
def get_invite_info(
    token: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    invite = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
    if not invite:
        raise HTTPException(404, "Invite not found or expired")

    if invite.status != InviteStatus.pending:
        raise HTTPException(400, f"Invite is {invite.status.value}")

    if invite.expires_at and invite.expires_at < _utcnow():
        invite.status = InviteStatus.expired
        db.commit()
        raise HTTPException(400, "Invite has expired")

    return {
        "token": invite.token,
        "project_name": invite.project.name,
        "project_slug": invite.project.slug,
        "role": invite.role.value,
        "created_by": invite.created_by.user_id if invite.created_by else None,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


@router.post("/invites/{token}/accept")
def accept_invite(
    token: str,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    invite = db.query(ProjectInvite).filter(ProjectInvite.token == token).first()
    if not invite:
        raise HTTPException(404, "Invite not found")

    if invite.status != InviteStatus.pending:
        raise HTTPException(400, f"Invite is {invite.status.value}")

    if invite.expires_at and invite.expires_at < _utcnow():
        invite.status = InviteStatus.expired
        db.commit()
        raise HTTPException(400, "Invite has expired")

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == invite.project_id,
        ProjectMember.user_id == auth.db_user.id,
    ).first()
    if existing:
        raise HTTPException(409, "You are already a member of this project")

    member = ProjectMember(
        project_id=invite.project_id,
        user_id=auth.db_user.id,
        role=invite.role,
    )
    db.add(member)

    invite.status = InviteStatus.accepted
    invite.accepted_by_id = auth.db_user.id
    invite.accepted_at = _utcnow()
    db.commit()

    return {
        "message": f"Joined project '{invite.project.name}' as {invite.role.value}",
        "project_slug": invite.project.slug,
    }


def _invite_dict(invite: ProjectInvite) -> dict:
    return {
        "id": str(invite.id),
        "token": invite.token,
        "role": invite.role.value,
        "status": invite.status.value,
        "created_by": invite.created_by.user_id if invite.created_by else None,
        "accepted_by": invite.accepted_by.user_id if invite.accepted_by else None,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
        "accepted_at": invite.accepted_at.isoformat() if invite.accepted_at else None,
    }


def _project_dict(project: Project, role: Optional[ProjectRole]) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "owner_id": str(project.owner_id),
        "owner_username": project.owner.user_id if project.owner else None,
        "member_count": len(project.members) if project.members is not None else 0,
        "my_role": role.value if role else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }
