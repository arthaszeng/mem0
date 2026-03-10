from typing import Optional
from uuid import UUID

from app.database import get_db
from app.models import App, Memory, MemoryAccessLog, MemoryState
from app.utils.gateway_auth import AuthenticatedUser, get_authenticated_user
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])


def get_app_or_404(db: Session, app_id: UUID) -> App:
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


@router.get("/")
async def list_apps(
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = 'name',
    sort_direction: str = 'asc',
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    memory_counts = db.query(
        Memory.app_id,
        func.count(Memory.id).label('memory_count')
    ).filter(
        Memory.state.in_([MemoryState.active, MemoryState.paused, MemoryState.archived]),
        Memory.user_id == auth.db_user.id,
    ).group_by(Memory.app_id).subquery()

    access_counts = db.query(
        MemoryAccessLog.app_id,
        func.count(func.distinct(MemoryAccessLog.memory_id)).label('access_count')
    ).group_by(MemoryAccessLog.app_id).subquery()

    query = db.query(
        App,
        func.coalesce(memory_counts.c.memory_count, 0).label('total_memories_created'),
        func.coalesce(access_counts.c.access_count, 0).label('total_memories_accessed')
    ).filter(App.owner_id == auth.db_user.id)

    query = query.outerjoin(
        memory_counts, App.id == memory_counts.c.app_id
    ).outerjoin(
        access_counts, App.id == access_counts.c.app_id
    )

    if name:
        query = query.filter(App.name.ilike(f"%{name}%"))
    if is_active is not None:
        query = query.filter(App.is_active == is_active)

    if sort_by == 'name':
        sort_field = App.name
    elif sort_by == 'memories':
        sort_field = func.coalesce(memory_counts.c.memory_count, 0)
    elif sort_by == 'memories_accessed':
        sort_field = func.coalesce(access_counts.c.access_count, 0)
    else:
        sort_field = App.name

    if sort_direction == 'desc':
        query = query.order_by(desc(sort_field))
    else:
        query = query.order_by(sort_field)

    total = query.count()
    apps = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "apps": [
            {
                "id": app[0].id,
                "name": app[0].name,
                "is_active": app[0].is_active,
                "total_memories_created": app[1],
                "total_memories_accessed": app[2]
            }
            for app in apps
        ]
    }


@router.get("/{app_id}")
async def get_app_details(
    app_id: UUID,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    app = get_app_or_404(db, app_id)
    if app.owner_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Access denied")

    access_stats = db.query(
        func.count(MemoryAccessLog.id).label("total_memories_accessed"),
        func.min(MemoryAccessLog.accessed_at).label("first_accessed"),
        func.max(MemoryAccessLog.accessed_at).label("last_accessed")
    ).filter(MemoryAccessLog.app_id == app_id).first()

    return {
        "is_active": app.is_active,
        "total_memories_created": db.query(Memory).filter(Memory.app_id == app_id).count(),
        "total_memories_accessed": access_stats.total_memories_accessed or 0,
        "first_accessed": access_stats.first_accessed,
        "last_accessed": access_stats.last_accessed
    }


@router.get("/{app_id}/memories")
async def list_app_memories(
    app_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    app = get_app_or_404(db, app_id)
    if app.owner_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Access denied")

    query = db.query(Memory).filter(
        Memory.app_id == app_id,
        Memory.state.in_([MemoryState.active, MemoryState.paused, MemoryState.archived])
    ).options(joinedload(Memory.categories))
    total = query.count()
    memories = query.order_by(Memory.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "created_at": m.created_at,
                "state": m.state.value,
                "app_id": m.app_id,
                "categories": [c.name for c in m.categories],
                "metadata_": m.metadata_
            }
            for m in memories
        ]
    }


@router.get("/{app_id}/accessed")
async def list_app_accessed_memories(
    app_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(
        Memory,
        func.count(MemoryAccessLog.id).label("access_count")
    ).join(
        MemoryAccessLog, Memory.id == MemoryAccessLog.memory_id
    ).filter(
        MemoryAccessLog.app_id == app_id
    ).group_by(Memory.id).order_by(desc("access_count"))

    query = query.options(joinedload(Memory.categories))

    total = query.count()
    results = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "memories": [
            {
                "memory": {
                    "id": memory.id,
                    "content": memory.content,
                    "created_at": memory.created_at,
                    "state": memory.state.value,
                    "app_id": memory.app_id,
                    "app_name": memory.app.name if memory.app else None,
                    "categories": [c.name for c in memory.categories],
                    "metadata_": memory.metadata_
                },
                "access_count": count
            }
            for memory, count in results
        ]
    }


@router.put("/{app_id}")
async def update_app_details(
    app_id: UUID,
    is_active: bool,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    app = get_app_or_404(db, app_id)
    if app.owner_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Access denied")
    app.is_active = is_active
    db.commit()
    return {"status": "success", "message": "Updated app details successfully"}
