from typing import Optional

from app.database import get_db
from app.models import App, Memory, MemoryState
from app.utils.gateway_auth import AuthenticatedUser, get_authenticated_user, resolve_project
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("")
async def get_profile(
    user_id: Optional[str] = None,
    project_slug: Optional[str] = None,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, project_slug)
    user = auth.db_user

    mem_q = db.query(Memory).filter(Memory.state != MemoryState.deleted)
    if pctx:
        mem_q = mem_q.filter(Memory.project_id == pctx.project_id)
    else:
        mem_q = mem_q.filter(Memory.user_id == user.id)
    total_memories = mem_q.count()

    apps = db.query(App).filter(App.owner_id == user.id)
    total_apps = apps.count()

    return {
        "total_memories": total_memories,
        "total_apps": total_apps,
        "apps": apps.all(),
    }
