import asyncio
import logging
from datetime import UTC, datetime
from typing import List, Optional, Set
from uuid import UUID

from app.database import get_db
from app.models import (
    AccessControl,
    App,
    Category,
    Memory,
    MemoryAccessLog,
    MemoryState,
    MemoryStatusHistory,
    ProjectRole,
    User,
)
from app.schemas import MemoryResponse
from app.utils.gateway_auth import AuthenticatedUser, get_authenticated_user, resolve_project
from app.utils.memory import get_memory_client
from app.utils.permissions import check_memory_access_permissions
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlalchemy import paginate as sqlalchemy_paginate
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from app.utils.categorization import match_domain_by_keywords
from app.utils.sensitive import sanitize_text

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


def get_memory_or_404(db: Session, memory_id: UUID) -> Memory:
    memory = db.query(Memory).filter(Memory.id == memory_id).first()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


def update_memory_state(db: Session, memory_id: UUID, new_state: MemoryState, user_id: UUID):
    memory = get_memory_or_404(db, memory_id)
    old_state = memory.state

    # Update memory state
    memory.state = new_state
    if new_state == MemoryState.archived:
        memory.archived_at = datetime.now(UTC)
    elif new_state == MemoryState.deleted:
        memory.deleted_at = datetime.now(UTC)

    # Record state change
    history = MemoryStatusHistory(
        memory_id=memory_id,
        changed_by=user_id,
        old_state=old_state,
        new_state=new_state
    )
    db.add(history)
    db.commit()
    return memory


def get_accessible_memory_ids(db: Session, app_id: UUID) -> Set[UUID]:
    """
    Get the set of memory IDs that the app has access to based on app-level ACL rules.
    Returns all memory IDs if no specific restrictions are found.
    """
    # Get app-level access controls
    app_access = db.query(AccessControl).filter(
        AccessControl.subject_type == "app",
        AccessControl.subject_id == app_id,
        AccessControl.object_type == "memory"
    ).all()

    # If no app-level rules exist, return None to indicate all memories are accessible
    if not app_access:
        return None

    # Initialize sets for allowed and denied memory IDs
    allowed_memory_ids = set()
    denied_memory_ids = set()

    # Process app-level rules
    for rule in app_access:
        if rule.effect == "allow":
            if rule.object_id:  # Specific memory access
                allowed_memory_ids.add(rule.object_id)
            else:  # All memories access
                return None  # All memories allowed
        elif rule.effect == "deny":
            if rule.object_id:  # Specific memory denied
                denied_memory_ids.add(rule.object_id)
            else:  # All memories denied
                return set()  # No memories accessible

    # Remove denied memories from allowed set
    if allowed_memory_ids:
        allowed_memory_ids -= denied_memory_ids

    return allowed_memory_ids


class SearchMemoryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    limit: int = 100
    threshold: float = 0.0
    project_slug: Optional[str] = None


@router.post("/search")
async def search_memories_semantic(
    request: SearchMemoryRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Semantic vector search over memories using the configured embedder + Qdrant."""
    pctx = resolve_project(auth, db, request.project_slug)

    memory_client = get_memory_client()
    if not memory_client:
        raise HTTPException(status_code=503, detail="Memory client unavailable")

    qdrant_filters = [FieldCondition(key="user_id", match=MatchValue(value=auth.username))]
    if pctx:
        qdrant_filters.append(FieldCondition(key="project_id", match=MatchValue(value=str(pctx.project_id))))
    query_filter = Filter(must=qdrant_filters)

    def _do_search():
        emb = memory_client.embedding_model.embed(request.query, "search")
        return memory_client.vector_store.client.query_points(
            collection_name=memory_client.vector_store.collection_name,
            query=emb,
            query_filter=query_filter,
            limit=request.limit,
        ).points

    hits = await asyncio.to_thread(_do_search)

    results = []
    for h in hits:
        payload = h.payload or {}
        score = h.score if hasattr(h, "score") else 0
        if score < request.threshold:
            continue
        results.append({
            "id": str(h.id),
            "memory": payload.get("data", ""),
            "hash": payload.get("hash"),
            "score": score,
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "metadata": {
                k: v for k, v in payload.items()
                if k not in ("data", "hash", "created_at", "updated_at")
            },
        })

    user = auth.db_user
    matched_domain = match_domain_by_keywords(request.query)
    if matched_domain:
        seen_ids = {r["id"] for r in results}
        domain_filters = [
            Memory.state == MemoryState.active,
            Memory.metadata_.op("->>")("domain") == matched_domain,
        ]
        if pctx:
            domain_filters.append(Memory.project_id == pctx.project_id)
        else:
            domain_filters.append(Memory.user_id == user.id)
        domain_q = db.query(Memory).filter(*domain_filters)
        domain_memories = domain_q.limit(request.limit).all()
        for dm in domain_memories:
            mid = str(dm.id)
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            results.append({
                "id": mid,
                "memory": dm.content,
                "hash": None,
                "score": 0.5,
                "created_at": dm.created_at.isoformat() if dm.created_at else None,
                "updated_at": dm.updated_at.isoformat() if dm.updated_at else None,
                "metadata": dm.metadata_ or {},
            })

    return {"results": results}


# List all memories with filtering
@router.get("/", response_model=Page[MemoryResponse])
async def list_memories(
    user_id: Optional[str] = None,
    app_id: Optional[UUID] = None,
    project_slug: Optional[str] = None,
    from_date: Optional[int] = Query(
        None,
        description="Filter memories created after this date (timestamp)",
        examples=[1718505600]
    ),
    to_date: Optional[int] = Query(
        None,
        description="Filter memories created before this date (timestamp)",
        examples=[1718505600]
    ),
    categories: Optional[str] = None,
    params: Params = Depends(),
    search_query: Optional[str] = None,
    sort_column: Optional[str] = Query(None, description="Column to sort by (memory, categories, app_name, created_at)"),
    sort_direction: Optional[str] = Query(None, description="Sort direction (asc or desc)"),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    pctx = resolve_project(auth, db, project_slug)
    user = auth.db_user

    base_filters = [
        Memory.state != MemoryState.deleted,
        Memory.state != MemoryState.archived,
    ]
    if pctx:
        base_filters.append(Memory.project_id == pctx.project_id)
    else:
        base_filters.append(Memory.user_id == user.id)

    if search_query:
        matched_domain = match_domain_by_keywords(search_query)
        search_conditions = [Memory.content.ilike(f"%{search_query}%")]
        if matched_domain:
            search_conditions.append(
                Memory.metadata_.op("->>")("domain") == matched_domain
            )
        base_filters.append(or_(*search_conditions))

    query = db.query(Memory).filter(*base_filters)

    # Apply filters
    if app_id:
        query = query.filter(Memory.app_id == app_id)

    if from_date:
        from_datetime = datetime.fromtimestamp(from_date, tz=UTC)
        query = query.filter(Memory.created_at >= from_datetime)

    if to_date:
        to_datetime = datetime.fromtimestamp(to_date, tz=UTC)
        query = query.filter(Memory.created_at <= to_datetime)

    # Add joins for app and categories after filtering
    query = query.outerjoin(App, Memory.app_id == App.id)
    query = query.outerjoin(Memory.categories)

    # Apply category filter if provided
    if categories:
        category_list = [c.strip() for c in categories.split(",")]
        query = query.filter(Category.name.in_(category_list))

    # Apply sorting if specified
    if sort_column:
        sort_field = getattr(Memory, sort_column, None)
        if sort_field:
            query = query.order_by(sort_field.desc()) if sort_direction == "desc" else query.order_by(sort_field.asc())

    # Add eager loading for app and categories
    query = query.options(
        joinedload(Memory.app),
        joinedload(Memory.categories)
    ).distinct(Memory.id)

    # Get paginated results with transformer
    return sqlalchemy_paginate(
        query,
        params,
        transformer=lambda items: [
            MemoryResponse(
                id=memory.id,
                content=memory.content,
                created_at=memory.created_at,
                state=memory.state.value,
                app_id=memory.app_id,
                app_name=memory.app.name if memory.app else None,
                created_by=memory.user.user_id if memory.user else None,
                categories=[category.name for category in memory.categories],
                metadata_=memory.metadata_
            )
            for memory in items
            if check_memory_access_permissions(db, memory, app_id)
        ]
    )


# Get all categories
@router.get("/categories")
async def get_categories(
    user_id: Optional[str] = None,
    project_slug: Optional[str] = None,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, project_slug)
    user = auth.db_user

    q = db.query(Memory).filter(Memory.state != MemoryState.deleted, Memory.state != MemoryState.archived)
    if pctx:
        q = q.filter(Memory.project_id == pctx.project_id)
    else:
        q = q.filter(Memory.user_id == user.id)
    memories = q.all()
    categories = [category for memory in memories for category in memory.categories]
    unique_categories = list(set(categories))

    return {
        "categories": unique_categories,
        "total": len(unique_categories)
    }


@router.get("/domains")
async def get_domains(
    user_id: Optional[str] = None,
    project_slug: Optional[str] = None,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, project_slug)
    user = auth.db_user

    domain_filters = [
        Memory.state != MemoryState.deleted,
        Memory.state != MemoryState.archived,
        Memory.metadata_.isnot(None),
    ]
    if pctx:
        domain_filters.append(Memory.project_id == pctx.project_id)
    else:
        domain_filters.append(Memory.user_id == user.id)
    domain_q = db.query(func.json_extract(Memory.metadata_, "$.domain")).filter(*domain_filters)
    results = domain_q.distinct().all()
    domains = sorted([r[0] for r in results if r[0]])
    return {"domains": domains, "total": len(domains)}


class CreateMemoryRequest(BaseModel):
    user_id: Optional[str] = None
    text: str
    metadata: dict = {}
    infer: bool = True
    app: str = "openmemory"
    project_slug: Optional[str] = None


class RegisterMemoryRequest(BaseModel):
    memory_id: str
    content: str
    user_id: Optional[str] = None
    app: str = "openclaw"
    metadata: dict = {}


class RegisterBatchRequest(BaseModel):
    memories: List[RegisterMemoryRequest]


@router.post("/register")
async def register_external_memory(
    request: RegisterMemoryRequest,
    background_tasks: BackgroundTasks,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Register a memory that already exists in Qdrant into SQLite.
    Used by external clients (e.g. OpenClaw JS SDK) that write to Qdrant
    directly but need the memory visible in the OpenMemory UI."""
    from app.models import categorize_memory_background

    user = auth.db_user

    app_obj = db.query(App).filter(App.name == request.app, App.owner_id == user.id).first()
    if not app_obj:
        app_obj = App(name=request.app, owner_id=user.id)
        db.add(app_obj)
        db.commit()
        db.refresh(app_obj)

    memory_id = UUID(request.memory_id)
    existing = db.query(Memory).filter(Memory.id == memory_id).first()
    if existing:
        existing.content = request.content
        existing.state = MemoryState.active
        db.commit()
        return {"status": "updated", "id": str(memory_id)}

    memory = Memory(
        id=memory_id,
        user_id=user.id,
        app_id=app_obj.id,
        content=request.content,
        metadata_=request.metadata,
        state=MemoryState.active,
    )
    db.add(memory)
    db.commit()

    background_tasks.add_task(categorize_memory_background, memory_id, request.content)
    return {"status": "created", "id": str(memory_id)}


@router.post("/register/batch")
async def register_external_memories_batch(
    request: RegisterBatchRequest,
    background_tasks: BackgroundTasks,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Batch register multiple Qdrant-only memories into SQLite."""
    from app.models import categorize_memory_background

    user = auth.db_user
    results = []
    for item in request.memories:
        app_obj = db.query(App).filter(App.name == item.app, App.owner_id == user.id).first()
        if not app_obj:
            app_obj = App(name=item.app, owner_id=user.id)
            db.add(app_obj)
            db.flush()

        memory_id = UUID(item.memory_id)
        existing = db.query(Memory).filter(Memory.id == memory_id).first()
        if existing:
            existing.content = item.content
            existing.state = MemoryState.active
            results.append({"status": "updated", "id": str(memory_id)})
        else:
            memory = Memory(
                id=memory_id,
                user_id=user.id,
                app_id=app_obj.id,
                content=item.content,
                metadata_=item.metadata,
                state=MemoryState.active,
            )
            db.add(memory)
            results.append({"status": "created", "id": str(memory_id)})
            background_tasks.add_task(categorize_memory_background, memory_id, item.content)

    db.commit()
    return {"results": results}


@router.post("/backfill-categories")
async def backfill_categories(
    user_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Trigger categorization for all memories that have no categories yet."""
    from app.models import categorize_memory_background

    user = auth.db_user

    uncategorized = (
        db.query(Memory)
        .outerjoin(Memory.categories)
        .filter(
            Memory.user_id == user.id,
            Memory.state == MemoryState.active,
            Category.id.is_(None),
        )
        .all()
    )

    for mem in uncategorized:
        background_tasks.add_task(categorize_memory_background, mem.id, mem.content)

    return {"scheduled": len(uncategorized), "memory_ids": [str(m.id) for m in uncategorized]}


# Create new memory
@router.post("/")
async def create_memory(
    request: CreateMemoryRequest,
    background_tasks: BackgroundTasks,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, request.project_slug, min_role=ProjectRole.read_write)
    user = auth.db_user

    app_obj = db.query(App).filter(App.name == request.app,
                                   App.owner_id == user.id).first()
    if not app_obj:
        app_obj = App(name=request.app, owner_id=user.id)
        db.add(app_obj)
        db.commit()
        db.refresh(app_obj)

    # Check if app is active
    if not app_obj.is_active:
        raise HTTPException(status_code=403, detail=f"App {request.app} is currently paused on OpenMemory. Cannot create new memories.")

    from app.models import categorize_memory_background

    logging.info(f"Creating memory for user: {auth.username} with app: {request.app}")

    safe_text = sanitize_text(request.text)

    try:
        memory_client = get_memory_client()
        if not memory_client:
            raise Exception("Memory client is not available")
    except Exception as client_error:
        logging.warning(f"Memory client unavailable: {client_error}. Creating memory in database only.")
        return {
            "error": str(client_error)
        }

    qdrant_meta = {
        "source_app": "openmemory",
        "mcp_client": request.app,
    }
    if pctx:
        qdrant_meta["project_id"] = str(pctx.project_id)

    try:
        qdrant_response = memory_client.add(
            safe_text,
            user_id=auth.username,
            metadata=qdrant_meta,
            infer=request.infer
        )
        
        # Log the response for debugging
        logging.info(f"Qdrant response: {qdrant_response}")
        
        # Process Qdrant response
        if isinstance(qdrant_response, dict) and 'results' in qdrant_response:
            changed_memories = []

            for result in qdrant_response['results']:
                memory_id = UUID(result['id'])
                existing_memory = db.query(Memory).filter(Memory.id == memory_id).first()

                if result['event'] in ('ADD', 'UPDATE'):
                    if existing_memory:
                        existing_memory.state = MemoryState.active
                        existing_memory.content = result['memory']
                        if pctx and not existing_memory.project_id:
                            existing_memory.project_id = pctx.project_id
                        memory = existing_memory
                    else:
                        memory = Memory(
                            id=memory_id,
                            user_id=user.id,
                            app_id=app_obj.id,
                            project_id=pctx.project_id if pctx else None,
                            content=result['memory'],
                            metadata_=request.metadata,
                            state=MemoryState.active
                        )
                        db.add(memory)

                    if result['event'] == 'ADD':
                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            old_state=MemoryState.deleted,
                            new_state=MemoryState.active
                        )
                        db.add(history)

                    changed_memories.append(memory)

            if changed_memories:
                db.commit()
                for memory in changed_memories:
                    db.refresh(memory)

                for memory in changed_memories:
                    background_tasks.add_task(
                        categorize_memory_background, memory.id, memory.content
                    )

                return changed_memories[0]
    except Exception as qdrant_error:
        logging.warning(f"Qdrant operation failed: {qdrant_error}.")
        # Return a json response with the error
        return {
            "error": str(qdrant_error)
        }




# Get memory by ID
@router.get("/{memory_id}")
async def get_memory(
    memory_id: UUID,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    memory = get_memory_or_404(db, memory_id)
    if memory.user_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Access denied")
    return {
        "id": memory.id,
        "text": memory.content,
        "created_at": int(memory.created_at.timestamp()),
        "state": memory.state.value,
        "app_id": memory.app_id,
        "app_name": memory.app.name if memory.app else None,
        "created_by": memory.user.user_id if memory.user else None,
        "categories": [category.name for category in memory.categories],
        "metadata_": memory.metadata_
    }


class DeleteMemoriesRequest(BaseModel):
    memory_ids: List[UUID]
    user_id: Optional[str] = None
    project_slug: Optional[str] = None

# Delete multiple memories
@router.delete("/")
async def delete_memories(
    request: DeleteMemoriesRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, request.project_slug, min_role=ProjectRole.read_write)
    user = auth.db_user

    # Get memory client to delete from vector store
    try:
        memory_client = get_memory_client()
        if not memory_client:
            raise HTTPException(
                status_code=503,
                detail="Memory client is not available"
            )
    except HTTPException:
        raise
    except Exception as client_error:
        logging.error(f"Memory client initialization failed: {client_error}")
        raise HTTPException(
            status_code=503,
            detail=f"Memory service unavailable: {str(client_error)}"
        )

    for memory_id in request.memory_ids:
        memory = get_memory_or_404(db, memory_id)
        if not auth.is_superadmin and memory.user_id != user.id:
            raise HTTPException(403, f"No permission to delete memory {memory_id}")
        if pctx and memory.project_id != pctx.project_id:
            raise HTTPException(403, f"Memory {memory_id} does not belong to this project")

        try:
            memory_client.delete(str(memory_id))
        except Exception as delete_error:
            logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

        update_memory_state(db, memory_id, MemoryState.deleted, user.id)

    return {"message": f"Successfully deleted {len(request.memory_ids)} memories"}


class ArchiveMemoriesRequest(BaseModel):
    memory_ids: List[UUID]
    project_slug: Optional[str] = None


@router.post("/actions/archive")
async def archive_memories(
    request: ArchiveMemoriesRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, request.project_slug, min_role=ProjectRole.read_write)
    user = auth.db_user

    for memory_id in request.memory_ids:
        memory = get_memory_or_404(db, memory_id)
        if not auth.is_superadmin and memory.user_id != user.id:
            raise HTTPException(403, f"No permission to archive memory {memory_id}")
        if pctx and memory.project_id != pctx.project_id:
            raise HTTPException(403, f"Memory {memory_id} does not belong to this project")
        update_memory_state(db, memory_id, MemoryState.archived, user.id)
    return {"message": f"Successfully archived {len(request.memory_ids)} memories"}


class PauseMemoriesRequest(BaseModel):
    memory_ids: Optional[List[UUID]] = None
    category_ids: Optional[List[UUID]] = None
    app_id: Optional[UUID] = None
    all_for_app: bool = False
    global_pause: bool = False
    state: Optional[MemoryState] = None
    user_id: Optional[str] = None

# Pause access to memories
@router.post("/actions/pause")
async def pause_memories(
    request: PauseMemoriesRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    global_pause = request.global_pause
    all_for_app = request.all_for_app
    app_id = request.app_id
    memory_ids = request.memory_ids
    category_ids = request.category_ids
    state = request.state or MemoryState.paused

    user = auth.db_user
    user_id = user.id
    
    if global_pause:
        q = db.query(Memory).filter(
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived,
        )
        if not auth.is_superadmin:
            q = q.filter(Memory.user_id == user.id)
        memories = q.all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": "Successfully paused all memories"}

    if app_id:
        # Pause all memories for an app
        memories = db.query(Memory).filter(
            Memory.app_id == app_id,
            Memory.user_id == user.id,
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": f"Successfully paused all memories for app {app_id}"}
    
    if all_for_app and memory_ids:
        # Pause all memories for an app
        memories = db.query(Memory).filter(
            Memory.user_id == user.id,
            Memory.state != MemoryState.deleted,
            Memory.id.in_(memory_ids)
        ).all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": "Successfully paused all memories"}

    if memory_ids:
        # Pause specific memories
        for memory_id in memory_ids:
            update_memory_state(db, memory_id, state, user_id)
        return {"message": f"Successfully paused {len(memory_ids)} memories"}

    if category_ids:
        q = db.query(Memory).join(Memory.categories).filter(
            Category.id.in_(category_ids),
            Memory.state != MemoryState.deleted,
            Memory.state != MemoryState.archived,
        )
        if not auth.is_superadmin:
            q = q.filter(Memory.user_id == user.id)
        memories = q.all()
        for memory in memories:
            update_memory_state(db, memory.id, state, user_id)
        return {"message": f"Successfully paused memories in {len(category_ids)} categories"}

    raise HTTPException(status_code=400, detail="Invalid pause request parameters")


# Get memory access logs
@router.get("/{memory_id}/access-log")
async def get_memory_access_log(
    memory_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    query = db.query(MemoryAccessLog).filter(MemoryAccessLog.memory_id == memory_id)
    total = query.count()
    logs = query.order_by(MemoryAccessLog.accessed_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # Get app name
    for log in logs:
        app = db.query(App).filter(App.id == log.app_id).first()
        log.app_name = app.name if app else None

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "logs": logs
    }


class UpdateMemoryRequest(BaseModel):
    memory_content: str
    user_id: Optional[str] = None

# Update a memory
@router.put("/{memory_id}")
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    memory = get_memory_or_404(db, memory_id)
    if memory.user_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Cannot update another user's memory")
    memory.content = request.memory_content
    db.commit()
    db.refresh(memory)
    return memory

class FilterMemoriesRequest(BaseModel):
    user_id: Optional[str] = None
    page: int = 1
    size: int = 10
    search_query: Optional[str] = None
    app_ids: Optional[List[UUID]] = None
    category_ids: Optional[List[UUID]] = None
    domains: Optional[List[str]] = None
    sort_column: Optional[str] = None
    sort_direction: Optional[str] = None
    from_date: Optional[int] = None
    to_date: Optional[int] = None
    show_archived: Optional[bool] = False
    project_slug: Optional[str] = None

@router.post("/filter", response_model=Page[MemoryResponse])
async def filter_memories(
    request: FilterMemoriesRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth, db, request.project_slug)
    user = auth.db_user

    base_project_filters = [
        Memory.state != MemoryState.deleted,
    ]
    if pctx:
        base_project_filters.append(Memory.project_id == pctx.project_id)
    else:
        base_project_filters.append(Memory.user_id == user.id)

    query = db.query(Memory).filter(*base_project_filters)

    # Filter archived memories based on show_archived parameter
    if not request.show_archived:
        query = query.filter(Memory.state != MemoryState.archived)

    # Apply search filter with domain-aware expansion
    if request.search_query:
        search_conditions = [Memory.content.ilike(f"%{request.search_query}%")]
        matched_domain = match_domain_by_keywords(request.search_query)
        if matched_domain:
            search_conditions.append(
                Memory.metadata_.op("->>")("domain") == matched_domain
            )
        query = query.filter(or_(*search_conditions))

    # Apply app filter
    if request.app_ids:
        query = query.filter(Memory.app_id.in_(request.app_ids))

    # Apply domain filter
    if request.domains:
        query = query.filter(
            func.json_extract(Memory.metadata_, "$.domain").in_(request.domains)
        )

    # Add joins for app and categories
    query = query.outerjoin(App, Memory.app_id == App.id)

    # Apply category filter
    if request.category_ids:
        query = query.join(Memory.categories).filter(Category.id.in_(request.category_ids))
    else:
        query = query.outerjoin(Memory.categories)

    # Apply date filters
    if request.from_date:
        from_datetime = datetime.fromtimestamp(request.from_date, tz=UTC)
        query = query.filter(Memory.created_at >= from_datetime)

    if request.to_date:
        to_datetime = datetime.fromtimestamp(request.to_date, tz=UTC)
        query = query.filter(Memory.created_at <= to_datetime)

    # Apply sorting
    if request.sort_column and request.sort_direction:
        sort_direction = request.sort_direction.lower()
        if sort_direction not in ['asc', 'desc']:
            raise HTTPException(status_code=400, detail="Invalid sort direction")

        sort_mapping = {
            'memory': Memory.content,
            'app_name': App.name,
            'created_at': Memory.created_at
        }

        if request.sort_column not in sort_mapping:
            raise HTTPException(status_code=400, detail="Invalid sort column")

        sort_field = sort_mapping[request.sort_column]
        if sort_direction == 'desc':
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field.asc())
    else:
        # Default sorting
        query = query.order_by(Memory.created_at.desc())

    # Add eager loading for categories and make the query distinct
    query = query.options(
        joinedload(Memory.categories)
    ).distinct(Memory.id)

    # Use fastapi-pagination's paginate function
    return sqlalchemy_paginate(
        query,
        Params(page=request.page, size=request.size),
        transformer=lambda items: [
            MemoryResponse(
                id=memory.id,
                content=memory.content,
                created_at=memory.created_at,
                state=memory.state.value,
                app_id=memory.app_id,
                app_name=memory.app.name if memory.app else None,
                created_by=memory.user.user_id if memory.user else None,
                categories=[category.name for category in memory.categories],
                metadata_=memory.metadata_
            )
            for memory in items
        ]
    )


@router.get("/{memory_id}/related", response_model=Page[MemoryResponse])
async def get_related_memories(
    memory_id: UUID,
    user_id: Optional[str] = None,
    params: Params = Depends(),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    user = auth.db_user
    
    # Get the source memory
    memory = get_memory_or_404(db, memory_id)
    
    # Extract category IDs from the source memory
    category_ids = [category.id for category in memory.categories]
    
    if not category_ids:
        return Page.create([], total=0, params=params)
    
    related_filters = [
        Memory.id != memory_id,
        Memory.state != MemoryState.deleted,
    ]
    if memory.project_id:
        related_filters.append(Memory.project_id == memory.project_id)
    else:
        related_filters.append(Memory.user_id == user.id)
    query = db.query(Memory).distinct(Memory.id).filter(
        *related_filters
    ).join(Memory.categories).filter(
        Category.id.in_(category_ids)
    ).options(
        joinedload(Memory.categories),
        joinedload(Memory.app)
    ).order_by(
        func.count(Category.id).desc(),
        Memory.created_at.desc()
    ).group_by(Memory.id)
    
    # ⚡ Force page size to be 5
    params = Params(page=params.page, size=5)
    
    return sqlalchemy_paginate(
        query,
        params,
        transformer=lambda items: [
            MemoryResponse(
                id=memory.id,
                content=memory.content,
                created_at=memory.created_at,
                state=memory.state.value,
                app_id=memory.app_id,
                app_name=memory.app.name if memory.app else None,
                created_by=memory.user.user_id if memory.user else None,
                categories=[category.name for category in memory.categories],
                metadata_=memory.metadata_
            )
            for memory in items
        ]
    )