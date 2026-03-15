import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import List, Optional, Set
from uuid import UUID

from app.database import get_db
from app.models import (
    AccessControl,

    App,
    ArchivePolicy,
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
from app.utils.insights import (
    compute_knowledge_coverage,
    compute_topic_trends,
    generate_user_profile,
)
from app.utils.sensitive import sanitize_text

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])

_profile_cache: dict[str, tuple[dict, datetime]] = {}


def _extract_entities_background(memory_id: UUID, content: str):
    """Background task: extract entities from memory and store in Kuzu graph."""
    try:
        from app.utils.entity_extraction import extract_entities
        from app.utils.graph_store import add_entities
        result = extract_entities(content)
        if result.get("entities"):
            add_entities(result["entities"], result.get("relations", []), str(memory_id))
            logging.info("Extracted %d entities from memory %s", len(result["entities"]), memory_id)
    except Exception as e:
        logging.warning("Entity extraction failed for %s: %s", memory_id, e)


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
    categories: Optional[List[str]] = None


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

    if request.categories:
        result_ids = [r["id"] for r in results]
        if result_ids:
            cat_mem_ids = set()
            cat_q = (
                db.query(Memory.id)
                .join(Memory.categories)
                .filter(Memory.id.in_([UUID(rid) for rid in result_ids]))
                .filter(Category.name.in_(request.categories))
            )
            cat_mem_ids = {str(row[0]) for row in cat_q.all()}
            results = [r for r in results if r["id"] in cat_mem_ids]

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
                metadata_=memory.metadata_,
                run_id=memory.run_id,
                expires_at=memory.expires_at,
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


def _require_superadmin(auth: AuthenticatedUser = Depends(get_authenticated_user)) -> AuthenticatedUser:
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin required")
    return auth


class ArchivePolicyCreate(BaseModel):
    criteria_type: str
    criteria_id: Optional[str] = None
    days_to_archive: int


class ArchivePolicyResponse(BaseModel):
    id: str
    criteria_type: str
    criteria_id: Optional[str]
    days_to_archive: int
    created_at: str


@router.get("/archive-policies", response_model=List[ArchivePolicyResponse])
async def list_archive_policies(
    auth: AuthenticatedUser = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    policies = db.query(ArchivePolicy).order_by(ArchivePolicy.created_at.desc()).all()
    return [
        ArchivePolicyResponse(
            id=str(p.id),
            criteria_type=p.criteria_type,
            criteria_id=str(p.criteria_id) if p.criteria_id else None,
            days_to_archive=p.days_to_archive,
            created_at=p.created_at.isoformat() if p.created_at else "",
        )
        for p in policies
    ]


@router.post("/archive-policies", response_model=ArchivePolicyResponse)
async def create_archive_policy(
    request: ArchivePolicyCreate,
    auth: AuthenticatedUser = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    if request.criteria_type not in ("global", "app"):
        raise HTTPException(400, "criteria_type must be 'global' or 'app'")
    if request.criteria_type == "app" and not request.criteria_id:
        raise HTTPException(400, "criteria_id required for app policy")
    if request.criteria_type == "global" and request.criteria_id:
        raise HTTPException(400, "criteria_id must be null for global policy")
    if request.days_to_archive < 1:
        raise HTTPException(400, "days_to_archive must be >= 1")

    policy = ArchivePolicy(
        criteria_type=request.criteria_type,
        criteria_id=request.criteria_id,
        days_to_archive=request.days_to_archive,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return ArchivePolicyResponse(
        id=str(policy.id),
        criteria_type=policy.criteria_type,
        criteria_id=str(policy.criteria_id) if policy.criteria_id else None,
        days_to_archive=policy.days_to_archive,
        created_at=policy.created_at.isoformat() if policy.created_at else "",
    )


@router.post("/archive-policies/apply")
async def apply_archive_policies_endpoint(
    auth: AuthenticatedUser = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    from app.utils.archive_policy import apply_archive_policies
    count = apply_archive_policies(session=db)
    return {"archived": count}


@router.delete("/archive-policies/{policy_id}")
async def delete_archive_policy(
    policy_id: UUID,
    auth: AuthenticatedUser = Depends(_require_superadmin),
    db: Session = Depends(get_db),
):
    policy = db.query(ArchivePolicy).filter(ArchivePolicy.id == policy_id).first()
    if not policy:
        raise HTTPException(404, "Archive policy not found")
    db.delete(policy)
    db.commit()
    return {"status": "deleted"}


class CreateMemoryRequest(BaseModel):
    user_id: Optional[str] = None
    text: str
    metadata: dict = {}
    infer: bool = True
    app: str = "memverse"
    project_slug: Optional[str] = None
    run_id: Optional[str] = None
    expires_at: Optional[str] = None


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
    directly but need the memory visible in the Memverse UI."""
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
        if existing.user_id != user.id and not auth.is_superadmin:
            raise HTTPException(403, f"No permission to update memory {memory_id}")
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
            if existing.user_id != user.id and not auth.is_superadmin:
                results.append({"status": "forbidden", "id": str(memory_id)})
                continue
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


@router.post("/backfill-entities")
async def backfill_entities(
    limit: int = Query(0, ge=0, description="0 = all active memories"),
    background_tasks: BackgroundTasks = None,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Extract entities from all active memories and populate the knowledge graph.
    Set limit=0 (default) to process all memories."""
    from app.utils.entity_extraction import extract_entities
    from app.utils.graph_store import add_entities

    user = auth.db_user
    q = (
        db.query(Memory)
        .filter(Memory.user_id == user.id, Memory.state == MemoryState.active)
        .order_by(Memory.updated_at.desc())
    )
    if limit > 0:
        q = q.limit(limit)
    memories = q.all()

    def _backfill_batch(mems):
        count = 0
        for mem in mems:
            try:
                result = extract_entities(mem.content)
                if result.get("entities"):
                    add_entities(result["entities"], result.get("relations", []), str(mem.id))
                    count += 1
            except Exception as e:
                logging.warning("Entity backfill failed for %s: %s", mem.id, e)
        logging.info("Backfill complete: %d/%d memories produced entities", count, len(mems))

    background_tasks.add_task(_backfill_batch, memories)

    return {"scheduled": len(memories), "memory_ids": [str(m.id) for m in memories]}


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
        raise HTTPException(status_code=403, detail=f"App {request.app} is currently paused on Memverse. Cannot create new memories.")

    from app.models import categorize_memory_background

    logging.info(f"Creating memory for user: {auth.username} with app: {request.app}")

    safe_text = sanitize_text(request.text)
    if not safe_text or not safe_text.strip():
        raise HTTPException(status_code=400, detail="Memory text must not be empty or whitespace-only")

    try:
        memory_client = get_memory_client()
        if not memory_client:
            raise Exception("Memory client is not available")
    except Exception as client_error:
        logging.warning(f"Memory client unavailable: {client_error}. Creating memory in database only.")
        raise HTTPException(status_code=503, detail="Memory service unavailable")

    qdrant_meta = {
        "source_app": "memverse",
        "mcp_client": request.app,
    }
    if pctx:
        qdrant_meta["project_id"] = str(pctx.project_id)
    if request.run_id:
        qdrant_meta["run_id"] = request.run_id
    if request.expires_at:
        qdrant_meta["expires_at"] = request.expires_at

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
                        from datetime import timezone
                        new_mem_kwargs = dict(
                            id=memory_id,
                            user_id=user.id,
                            app_id=app_obj.id,
                            project_id=pctx.project_id if pctx else None,
                            content=result['memory'],
                            metadata_=request.metadata,
                            state=MemoryState.active,
                        )
                        if request.run_id:
                            new_mem_kwargs["run_id"] = request.run_id
                        if request.expires_at:
                            from dateutil.parser import isoparse
                            new_mem_kwargs["expires_at"] = isoparse(request.expires_at)
                        memory = Memory(**new_mem_kwargs)
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
                    background_tasks.add_task(
                        _extract_entities_background, memory.id, memory.content
                    )

                return changed_memories[0]
    except Exception as qdrant_error:
        logging.warning(f"Qdrant operation failed: {qdrant_error}.")
        raise HTTPException(status_code=502, detail=f"Memory storage error: {qdrant_error}")




@router.get("/stats/analytics")
async def get_memory_analytics(
    project_slug: Optional[str] = Query(None),
    auth_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth_user, db, project_slug)
    user = auth_user.db_user

    base_filters = [Memory.state != MemoryState.deleted]
    if pctx:
        base_filters.append(Memory.project_id == pctx.project_id)
    else:
        base_filters.append(Memory.user_id == user.id)

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=30)

    growth_rows = (
        db.query(func.date(Memory.created_at).label("date"), func.count(Memory.id).label("count"))
        .filter(*base_filters, Memory.created_at >= datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC))
        .group_by(func.date(Memory.created_at))
        .order_by(func.date(Memory.created_at))
        .all()
    )
    growth_by_date = {str(r.date): r.count for r in growth_rows}
    cumulative = 0
    memory_growth = []
    for i in range(31):
        d = start_date + timedelta(days=i)
        if d > end_date:
            break
        date_str = d.isoformat()
        count = growth_by_date.get(date_str, 0)
        cumulative += count
        memory_growth.append({"date": date_str, "count": count, "cumulative": cumulative})

    cat_rows = (
        db.query(Category.name, func.count(Memory.id).label("count"))
        .join(Category.memories)
        .filter(*base_filters, Memory.state != MemoryState.archived)
        .group_by(Category.name)
        .order_by(func.count(Memory.id).desc())
        .all()
    )
    category_distribution = [{"name": r.name, "count": r.count} for r in cat_rows]

    now = datetime.now(UTC)
    seven_d_ago = now - timedelta(days=7)
    thirty_d_ago = now - timedelta(days=30)
    created_last_7d = db.query(func.count(Memory.id)).filter(*base_filters, Memory.created_at >= seven_d_ago).scalar() or 0
    created_last_30d = db.query(func.count(Memory.id)).filter(*base_filters, Memory.created_at >= thirty_d_ago).scalar() or 0
    archived_count = db.query(func.count(Memory.id)).filter(*base_filters, Memory.state == MemoryState.archived).scalar() or 0
    total_active = db.query(func.count(Memory.id)).filter(*base_filters, Memory.state == MemoryState.active).scalar() or 0

    return {
        "memory_growth": memory_growth,
        "category_distribution": category_distribution,
        "recent_activity": {
            "created_last_7d": created_last_7d,
            "created_last_30d": created_last_30d,
            "archived_count": archived_count,
            "total_active": total_active,
        },
    }


@router.get("/stats/insights")
async def get_memory_insights(
    project_slug: Optional[str] = Query(None),
    refresh: bool = Query(False, description="Regenerate user profile from LLM"),
    auth_user: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    pctx = resolve_project(auth_user, db, project_slug)
    user = auth_user.db_user

    base_filters = [
        Memory.state != MemoryState.deleted,
        Memory.state != MemoryState.archived,
    ]
    if pctx:
        base_filters.append(Memory.project_id == pctx.project_id)
    else:
        base_filters.append(Memory.user_id == user.id)

    memories_q = (
        db.query(Memory)
        .filter(*base_filters)
        .options(joinedload(Memory.categories))
        .order_by(Memory.created_at.desc())
    )
    memories = memories_q.all()

    memory_dicts = []
    cat_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for m in memories:
        cats = [c.name for c in m.categories]
        domain = (m.metadata_ or {}).get("domain", "")
        for c in cats:
            cat_counts[c] = cat_counts.get(c, 0) + 1
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        memory_dicts.append({
            "content": m.content,
            "categories": cats,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "metadata": m.metadata_ or {},
            "metadata_": m.metadata_ or {},
        })

    topic_trends = compute_topic_trends(memory_dicts, days=30)
    categories_list = [{"name": k, "count": v} for k, v in cat_counts.items()]
    domains_list = [{"name": k, "count": v} for k, v in domain_counts.items()]
    knowledge_coverage = compute_knowledge_coverage(
        categories_list, domains_list, total_memories=len(memories)
    )

    cache_key = f"{user.id}:{pctx.project_id if pctx else ''}"
    user_profile = None
    now = datetime.now(UTC)
    cache_ttl = timedelta(hours=1)
    if cache_key in _profile_cache:
        cached_profile, cached_at = _profile_cache[cache_key]
        if not refresh and (now - cached_at) < cache_ttl:
            user_profile = cached_profile

    if user_profile is None and memory_dicts:
        try:
            user_profile = await generate_user_profile(memory_dicts)
            if user_profile:
                _profile_cache[cache_key] = (user_profile, now)
        except Exception as e:
            logging.warning("Insights user profile generation failed: %s", e)

    return {
        "user_profile": user_profile,
        "topic_trends": topic_trends,
        "knowledge_coverage": knowledge_coverage,
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
        for memory_id in memory_ids:
            memory = get_memory_or_404(db, memory_id)
            if not auth.is_superadmin and memory.user_id != user.id:
                raise HTTPException(403, f"No permission to pause memory {memory_id}")
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
    memory = get_memory_or_404(db, memory_id)
    if not auth.is_superadmin and memory.user_id != auth.db_user.id:
        raise HTTPException(403, "No permission to view access logs for this memory")

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
    run_id: Optional[str] = None
    expires_at: Optional[str] = None


@router.put("/{memory_id}")
async def update_memory(
    memory_id: UUID,
    request: UpdateMemoryRequest,
    background_tasks: BackgroundTasks,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    memory = get_memory_or_404(db, memory_id)
    if memory.user_id != auth.db_user.id and not auth.is_superadmin:
        raise HTTPException(403, "Cannot update another user's memory")
    if not request.memory_content or not request.memory_content.strip():
        raise HTTPException(400, "Memory content must not be empty or whitespace-only")
    memory.content = request.memory_content
    if request.run_id is not None:
        memory.run_id = request.run_id
    if request.expires_at is not None:
        from dateutil.parser import isoparse
        memory.expires_at = isoparse(request.expires_at)
    db.commit()
    db.refresh(memory)

    from app.models import categorize_memory_background
    background_tasks.add_task(categorize_memory_background, memory.id, memory.content)

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
                metadata_=memory.metadata_,
                run_id=memory.run_id,
                expires_at=memory.expires_at,
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
    
    memory = get_memory_or_404(db, memory_id)
    if not auth.is_superadmin and memory.user_id != user.id:
        raise HTTPException(403, "No permission to view related memories")

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
                metadata_=memory.metadata_,
                run_id=memory.run_id,
                expires_at=memory.expires_at,
            )
            for memory in items
        ]
    )


# --- Phase 1b: New endpoints ---

class RestoreMemoryRequest(BaseModel):
    memory_ids: List[UUID]
    project_slug: Optional[str] = None


@router.post("/actions/restore")
async def restore_memories(
    request: RestoreMemoryRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Restore archived memories back to active state."""
    user = auth.db_user
    restored = []
    for mid in request.memory_ids:
        memory = get_memory_or_404(db, mid)
        if memory.user_id != user.id and not auth.is_superadmin:
            raise HTTPException(403, f"No permission to restore memory {mid}")
        if memory.state != MemoryState.archived:
            continue
        update_memory_state(db, mid, MemoryState.active, user.id)
        restored.append(str(mid))
    return {"restored": restored, "count": len(restored)}


class ExportMemoriesRequest(BaseModel):
    format: str = "json"
    categories: Optional[List[str]] = None
    project_slug: Optional[str] = None


@router.post("/export")
async def export_memories(
    request: ExportMemoriesRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Export memories, optionally filtered by category/type/agent, grouped by category."""
    pctx = resolve_project(auth, db, request.project_slug)
    user = auth.db_user

    filters = [Memory.state == MemoryState.active]
    if pctx:
        filters.append(Memory.project_id == pctx.project_id)
    else:
        filters.append(Memory.user_id == user.id)

    query = db.query(Memory).filter(*filters).options(joinedload(Memory.categories))

    if request.categories:
        query = query.join(Memory.categories).filter(Category.name.in_(request.categories))

    memories = query.all()

    grouped: dict = {}
    for mem in memories:
        cats = [c.name for c in mem.categories] or ["uncategorized"]
        for cat in cats:
            grouped.setdefault(cat, []).append({
                "id": str(mem.id),
                "content": mem.content,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            })

    if request.format == "text":
        lines = []
        for cat, items in grouped.items():
            lines.append(f"## {cat}")
            for item in items:
                lines.append(f"- {item['content']}")
            lines.append("")
        return {"format": "text", "content": "\n".join(lines), "total": len(memories)}

    return {"format": "json", "categories": grouped, "total": len(memories)}


class ConsolidateRequest(BaseModel):
    memory_ids: List[UUID]
    dry_run: bool = True
    project_slug: Optional[str] = None


@router.post("/consolidate")
async def consolidate_memories_endpoint(
    request: ConsolidateRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Consolidate (merge) similar memories into one using LLM."""
    user = auth.db_user
    memories_data = []
    for mid in request.memory_ids:
        mem = get_memory_or_404(db, mid)
        if mem.user_id != user.id and not auth.is_superadmin:
            raise HTTPException(403, f"No permission to consolidate memory {mid}")
        memories_data.append({"id": str(mid), "content": mem.content})

    from app.utils.intelligence import consolidate_memories as _consolidate
    consolidated_text = await asyncio.to_thread(_consolidate, memories_data)

    if not consolidated_text:
        raise HTTPException(500, "Consolidation failed — LLM unavailable or returned empty")

    result = {
        "consolidated_text": consolidated_text,
        "source_memory_ids": [str(mid) for mid in request.memory_ids],
        "dry_run": request.dry_run,
    }

    if not request.dry_run:
        first_mem = db.query(Memory).filter(Memory.id == request.memory_ids[0]).first()
        first_mem.content = consolidated_text
        for mid in request.memory_ids[1:]:
            update_memory_state(db, mid, MemoryState.archived, user.id)
        db.commit()
        result["kept_memory_id"] = str(request.memory_ids[0])

    return result


class ContradictionRequest(BaseModel):
    new_memory: str
    limit: int = 20
    project_slug: Optional[str] = None


@router.post("/check-contradiction")
async def check_contradiction_endpoint(
    request: ContradictionRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Check if a new memory text contradicts any existing memories."""
    pctx = resolve_project(auth, db, request.project_slug)
    user = auth.db_user

    filters = [Memory.state == MemoryState.active]
    if pctx:
        filters.append(Memory.project_id == pctx.project_id)
    else:
        filters.append(Memory.user_id == user.id)

    existing = db.query(Memory).filter(*filters).order_by(Memory.created_at.desc()).limit(request.limit).all()
    existing_data = [{"id": str(m.id), "content": m.content} for m in existing]

    from app.utils.intelligence import detect_contradiction
    result = await asyncio.to_thread(detect_contradiction, request.new_memory, existing_data)
    return result


# --- Entities router (graph) ---

entities_router = APIRouter(prefix="/api/v1/entities", tags=["entities"])


@entities_router.get("/")
async def list_graph_entities(
    limit: int = Query(100, ge=1, le=500),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """List all entities in the knowledge graph."""
    from app.utils.graph_store import list_entities
    entities = await asyncio.to_thread(list_entities, limit)
    return {"entities": entities, "total": len(entities)}


@entities_router.get("/search")
async def search_graph_entities(
    query: str = Query(..., description="Entity name to search for"),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
):
    """Search entities in the knowledge graph by name."""
    from app.utils.graph_store import search_entities
    results = await asyncio.to_thread(search_entities, query, limit)
    return {"entities": results, "total": len(results)}


@entities_router.get("/graph")
async def get_entities_graph(
    limit: int = Query(50, ge=1, le=200),
    project_slug: Optional[str] = Query(None),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Return full graph data (nodes + edges) for visualization."""
    from app.utils.graph_store import get_full_graph

    data = await asyncio.to_thread(get_full_graph, limit)

    if project_slug:
        pctx = resolve_project(auth, db, project_slug)
        if pctx:
            filters = [Memory.state == MemoryState.active, Memory.project_id == pctx.project_id]
        else:
            filters = [Memory.state == MemoryState.active, Memory.user_id == auth.db_user.id]
        project_memory_ids = {str(r[0]) for r in db.query(Memory.id).filter(*filters).all()}
        if project_memory_ids:
            valid_nodes = {
                n["id"] for n in data["nodes"]
                if any(mid in project_memory_ids for mid in n.get("memory_ids", []))
            }
            data["edges"] = [
                e for e in data["edges"]
                if e.get("memory_id") in project_memory_ids
                and e["source"] in valid_nodes
                and e["target"] in valid_nodes
            ]
            data["nodes"] = [n for n in data["nodes"] if n["id"] in valid_nodes]

    for n in data["nodes"]:
        n.pop("memory_ids", None)

    return data

