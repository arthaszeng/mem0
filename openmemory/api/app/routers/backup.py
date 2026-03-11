from datetime import UTC, datetime
import asyncio
import io
import json
import gzip
import logging
import zipfile
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointIdsList

from app.database import get_db
from app.models import (
    User, App, Memory, MemoryState, Category, memory_categories,
    MemoryStatusHistory, AccessControl, Project, ProjectMember,
    MemoryAccessLog,
)
from app.utils.memory import get_memory_client
from app.utils.gateway_auth import (
    AuthenticatedUser, get_authenticated_user, resolve_project, ProjectRole,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backup", tags=["backup"])

EMBED_BATCH_SIZE = 20
EMBED_TIMEOUT = 60          # seconds per batch embedding call
EMBED_MAX_RETRIES = 2       # retry on timeout before marking failed

# In-memory store for background import task progress
_import_tasks: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    if isinstance(dt, datetime):
        try:
            return dt.astimezone(UTC).isoformat()
        except Exception:
            return dt.replace(tzinfo=UTC).isoformat()
    return None


def _parse_iso(dt: Optional[str]) -> Optional[datetime]:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt)
    except Exception:
        try:
            return datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return None


def _get_user_default_project(db: Session, user: User) -> Optional[Project]:
    """Return the user's first owned project (personal default)."""
    member = (
        db.query(ProjectMember)
        .filter(ProjectMember.user_id == user.id, ProjectMember.role == ProjectRole.owner)
        .first()
    )
    if member:
        return db.query(Project).filter(Project.id == member.project_id).first()
    return None


def _batch_embed_and_upsert(
    items: List[Dict[str, Any]],
    memory_client: Any,
    task_state: Optional[dict] = None,
) -> Tuple[int, int]:
    """Embed and upsert items in batches. Returns (embedded, failed) counts."""
    vs = memory_client.vector_store
    embedder = memory_client.embedding_model
    embed_client = embedder.client
    model = embedder.config.model
    dims = getattr(embedder.config, "embedding_dims", None)

    timed_client = embed_client.with_options(timeout=EMBED_TIMEOUT)

    embedded = 0
    failed = 0
    total_batches = (len(items) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE

    for batch_idx, i in enumerate(range(0, len(items), EMBED_BATCH_SIZE)):
        batch = items[i : i + EMBED_BATCH_SIZE]
        texts = [it["content"].replace("\n", " ") for it in batch]

        vectors = None
        for attempt in range(EMBED_MAX_RETRIES + 1):
            try:
                kwargs: dict = {"input": texts, "model": model}
                if dims:
                    kwargs["dimensions"] = dims
                logger.info("Embed batch %d/%d (%d items), attempt %d", batch_idx + 1, total_batches, len(batch), attempt + 1)
                response = timed_client.embeddings.create(**kwargs)
                vectors = [d.embedding for d in response.data]
                break
            except Exception as e:
                logger.warning("Embed batch %d attempt %d failed: %s", batch_idx + 1, attempt + 1, e)
                if attempt == EMBED_MAX_RETRIES:
                    failed += len(batch)
                    if task_state is not None:
                        task_state["failed"] += len(batch)

        if vectors is None:
            continue

        payloads = [it["payload"] for it in batch]
        ids = [it["id"] for it in batch]

        try:
            vs.insert(vectors=vectors, payloads=payloads, ids=ids)
            embedded += len(batch)
        except Exception as e:
            logger.warning("Batch upsert failed (batch %d/%d): %s", batch_idx + 1, total_batches, e)
            failed += len(batch)
            if task_state is not None:
                task_state["failed"] += len(batch)
            continue

        if task_state is not None:
            task_state["embedded"] += len(batch)

    return embedded, failed


async def _embed_worker(task_id: str, items: List[Dict[str, Any]]) -> None:
    """Background task: batch-embed items and update _import_tasks progress."""
    state = _import_tasks.get(task_id)
    if not state:
        return

    memory_client = get_memory_client()
    if not memory_client or not hasattr(memory_client, "embedding_model"):
        state["done"] = True
        state["error"] = "Memory client unavailable"
        return

    try:
        await asyncio.to_thread(_batch_embed_and_upsert, items, memory_client, state)
    except Exception as e:
        logger.error("Embed worker %s failed: %s", task_id, e)
        state["error"] = str(e)
    finally:
        state["done"] = True


# ---------------------------------------------------------------------------
# 0. Data Management: migration, clear, reembed
# ---------------------------------------------------------------------------

@router.post("/migrate-project")
async def migrate_project_ids(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Backfill project_id on memories where it is NULL. Superadmin only."""
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin required")

    user = auth.db_user
    project = _get_user_default_project(db, user)
    if not project:
        raise HTTPException(400, "No default project found for user")

    orphan_memories = (
        db.query(Memory)
        .filter(Memory.user_id == user.id, Memory.project_id.is_(None))
        .all()
    )
    sqlite_count = len(orphan_memories)
    for m in orphan_memories:
        m.project_id = project.id
    db.commit()

    qdrant_count = 0
    memory_client = get_memory_client()
    if memory_client:
        vs = getattr(memory_client, "vector_store", None)
        if vs and hasattr(vs, "client"):
            collection = vs.collection_name
            offset = None
            while True:
                points, next_offset = vs.client.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(must=[
                        FieldCondition(key="user_id", match=MatchValue(value=user.user_id)),
                    ]),
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                ids_to_update = [pt.id for pt in points if not (pt.payload or {}).get("project_id")]
                if ids_to_update:
                    vs.client.set_payload(
                        collection_name=collection,
                        payload={"project_id": str(project.id)},
                        points=ids_to_update,
                    )
                    qdrant_count += len(ids_to_update)
                if next_offset is None:
                    break
                offset = next_offset

    return {
        "message": f"Migration complete for user '{user.user_id}'",
        "project_slug": project.slug,
        "project_name": project.name,
        "sqlite_updated": sqlite_count,
        "qdrant_updated": qdrant_count,
    }


@router.post("/clear-data")
async def clear_user_data(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Delete ALL memory data for the current user (SQLite + Qdrant).
    Preserves user, project, and app records. Superadmin only."""
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin required")

    user = auth.db_user
    memory_ids = [
        mid for (mid,) in db.query(Memory.id).filter(Memory.user_id == user.id).all()
    ]

    if memory_ids:
        db.query(MemoryAccessLog).filter(MemoryAccessLog.memory_id.in_(memory_ids)).delete(synchronize_session=False)
        db.execute(memory_categories.delete().where(memory_categories.c.memory_id.in_(memory_ids)))
        db.query(MemoryStatusHistory).filter(MemoryStatusHistory.memory_id.in_(memory_ids)).delete(synchronize_session=False)
        db.query(Memory).filter(Memory.id.in_(memory_ids)).delete(synchronize_session=False)
        db.commit()

    sqlite_deleted = len(memory_ids)

    qdrant_deleted = 0
    memory_client = get_memory_client()
    if memory_client:
        vs = getattr(memory_client, "vector_store", None)
        if vs and hasattr(vs, "client"):
            collection = vs.collection_name
            offset = None
            all_point_ids: list = []
            while True:
                points, next_offset = vs.client.scroll(
                    collection_name=collection,
                    scroll_filter=Filter(must=[
                        FieldCondition(key="user_id", match=MatchValue(value=user.user_id)),
                    ]),
                    limit=100,
                    offset=offset,
                    with_payload=False,
                    with_vectors=False,
                )
                all_point_ids.extend(pt.id for pt in points)
                if next_offset is None:
                    break
                offset = next_offset

            if all_point_ids:
                vs.client.delete(
                    collection_name=collection,
                    points_selector=PointIdsList(points=all_point_ids),
                )
                qdrant_deleted = len(all_point_ids)

    logger.info("Cleared %d SQLite memories + %d Qdrant points for user %s", sqlite_deleted, qdrant_deleted, user.user_id)
    return {
        "message": f"Cleared all memory data for '{user.user_id}'",
        "sqlite_deleted": sqlite_deleted,
        "qdrant_deleted": qdrant_deleted,
    }


@router.post("/reembed")
async def reembed_missing_vectors(
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """Re-embed memories missing from Qdrant using batch embedding. Superadmin only.
    Returns a task_id; embedding runs in the background."""
    if not auth.is_superadmin:
        raise HTTPException(403, "Superadmin required")

    user = auth.db_user
    memory_client = get_memory_client()
    if not memory_client or not hasattr(memory_client, "embedding_model"):
        raise HTTPException(503, "Memory client or embedding model unavailable")

    vs = getattr(memory_client, "vector_store", None)
    if not vs or not hasattr(vs, "client"):
        raise HTTPException(503, "Vector store unavailable")

    all_memories = (
        db.query(Memory)
        .options(joinedload(Memory.app))
        .filter(Memory.user_id == user.id, Memory.state == MemoryState.active)
        .all()
    )
    sqlite_ids = {str(m.id) for m in all_memories}
    mem_by_id = {str(m.id): m for m in all_memories}

    qdrant_ids: set = set()
    offset = None
    while True:
        points, next_offset = vs.client.scroll(
            collection_name=vs.collection_name,
            scroll_filter=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user.user_id)),
            ]),
            limit=100, offset=offset, with_payload=False, with_vectors=False,
        )
        qdrant_ids.update(str(pt.id) for pt in points)
        if next_offset is None:
            break
        offset = next_offset

    missing_ids = sqlite_ids - qdrant_ids

    embed_items = []
    for mid in missing_ids:
        m = mem_by_id[mid]
        content = m.content or ""
        if not content.strip():
            continue
        payload: dict = {
            "data": content,
            "user_id": user.user_id,
            "source_app": "openmemory",
            "mcp_client": m.app.name if m.app else "openmemory",
        }
        if m.project_id:
            payload["project_id"] = str(m.project_id)
        if m.created_at:
            payload["created_at"] = _iso(m.created_at)
        if m.updated_at:
            payload["updated_at"] = _iso(m.updated_at)
        embed_items.append({"id": str(m.id), "content": content, "payload": payload})

    task_id = uuid4().hex[:12]
    _import_tasks[task_id] = {
        "total": len(embed_items),
        "embedded": 0,
        "failed": 0,
        "done": False,
        "type": "reembed",
    }
    asyncio.create_task(_embed_worker(task_id, embed_items))

    return {
        "task_id": task_id,
        "sqlite_active": len(sqlite_ids),
        "qdrant_existing": len(qdrant_ids),
        "to_embed": len(embed_items),
    }


# ---------------------------------------------------------------------------
# Import task status
# ---------------------------------------------------------------------------

@router.get("/import-status/{task_id}")
async def import_status(task_id: str):
    """Poll background embedding progress."""
    state = _import_tasks.get(task_id)
    if not state:
        raise HTTPException(404, "Task not found")
    return state


# ---------------------------------------------------------------------------
# 1. Export
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    app_id: Optional[UUID] = None
    from_date: Optional[int] = None
    to_date: Optional[int] = None
    project_slug: Optional[str] = None
    include_vectors: bool = True


def _export_sqlite(
    db: Session,
    user: User,
    req: ExportRequest,
    project: Optional[Project] = None,
) -> Dict[str, Any]:
    time_filters = []
    if req.from_date:
        time_filters.append(Memory.created_at >= datetime.fromtimestamp(req.from_date, tz=UTC))
    if req.to_date:
        time_filters.append(Memory.created_at <= datetime.fromtimestamp(req.to_date, tz=UTC))

    mem_q = (
        db.query(Memory)
        .options(
            joinedload(Memory.categories),
            joinedload(Memory.app),
            joinedload(Memory.project),
            joinedload(Memory.user),
        )
        .filter(
            Memory.user_id == user.id,
            *(time_filters or []),
            *([Memory.app_id == req.app_id] if req.app_id else []),
            *([Memory.project_id == project.id] if project else []),
        )
    )

    memories = mem_q.all()
    memory_ids = [m.id for m in memories]

    app_ids = sorted({m.app_id for m in memories if m.app_id})
    apps = db.query(App).filter(App.id.in_(app_ids)).all() if app_ids else []
    cats = sorted({c for m in memories for c in m.categories}, key=lambda c: str(c.id))
    mc_rows = (
        db.execute(memory_categories.select().where(memory_categories.c.memory_id.in_(memory_ids))).fetchall()
        if memory_ids else []
    )
    history = (
        db.query(MemoryStatusHistory).filter(MemoryStatusHistory.memory_id.in_(memory_ids)).all()
        if memory_ids else []
    )
    acls = (
        db.query(AccessControl).filter(
            AccessControl.subject_type == "app",
            AccessControl.subject_id.in_(app_ids) if app_ids else False,
        ).all()
        if app_ids else []
    )

    project_ids = sorted({m.project_id for m in memories if m.project_id})
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all() if project_ids else []

    return {
        "user": {
            "id": str(user.id), "user_id": user.user_id, "name": user.name,
            "email": user.email, "metadata": user.metadata_,
            "created_at": _iso(user.created_at), "updated_at": _iso(user.updated_at),
        },
        "projects": [
            {"id": str(p.id), "name": p.name, "slug": p.slug,
             "owner_username": p.owner.user_id if p.owner else None, "description": p.description}
            for p in projects
        ],
        "apps": [
            {"id": str(a.id), "owner_id": str(a.owner_id), "name": a.name, "description": a.description,
             "metadata": a.metadata_, "is_active": a.is_active,
             "created_at": _iso(a.created_at), "updated_at": _iso(a.updated_at)}
            for a in apps
        ],
        "categories": [
            {"id": str(c.id), "name": c.name, "description": c.description,
             "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at)}
            for c in cats
        ],
        "memories": [
            {"id": str(m.id), "user_id": str(m.user_id),
             "app_id": str(m.app_id) if m.app_id else None,
             "app_name": m.app.name if m.app else None,
             "project_id": str(m.project_id) if m.project_id else None,
             "project_slug": m.project.slug if m.project else None,
             "creator_username": m.user.user_id if m.user else None,
             "content": m.content, "metadata": m.metadata_, "state": m.state.value,
             "created_at": _iso(m.created_at), "updated_at": _iso(m.updated_at),
             "archived_at": _iso(m.archived_at), "deleted_at": _iso(m.deleted_at),
             "category_ids": [str(c.id) for c in m.categories]}
            for m in memories
        ],
        "memory_categories": [{"memory_id": str(r.memory_id), "category_id": str(r.category_id)} for r in mc_rows],
        "status_history": [
            {"id": str(h.id), "memory_id": str(h.memory_id), "changed_by": str(h.changed_by),
             "old_state": h.old_state.value, "new_state": h.new_state.value, "changed_at": _iso(h.changed_at)}
            for h in history
        ],
        "access_controls": [
            {"id": str(ac.id), "subject_type": ac.subject_type,
             "subject_id": str(ac.subject_id) if ac.subject_id else None,
             "object_type": ac.object_type, "object_id": str(ac.object_id) if ac.object_id else None,
             "effect": ac.effect, "created_at": _iso(ac.created_at)}
            for ac in acls
        ],
        "export_meta": {
            "app_id_filter": str(req.app_id) if req.app_id else None,
            "project_slug_filter": req.project_slug,
            "from_date": req.from_date, "to_date": req.to_date,
            "version": "2", "generated_at": datetime.now(UTC).isoformat(),
        },
    }


def _export_logical_memories_gz(
    db: Session, *, user: User,
    app_id: Optional[UUID] = None, from_date: Optional[int] = None,
    to_date: Optional[int] = None, project: Optional[Project] = None,
) -> bytes:
    time_filters = []
    if from_date:
        time_filters.append(Memory.created_at >= datetime.fromtimestamp(from_date, tz=UTC))
    if to_date:
        time_filters.append(Memory.created_at <= datetime.fromtimestamp(to_date, tz=UTC))

    q = (
        db.query(Memory)
        .options(joinedload(Memory.categories), joinedload(Memory.app), joinedload(Memory.project))
        .filter(Memory.user_id == user.id, *(time_filters or []),
                *([Memory.project_id == project.id] if project else []))
    )
    if app_id:
        q = q.filter(Memory.app_id == app_id)

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for m in q.all():
            record = {
                "id": str(m.id), "content": m.content, "metadata": m.metadata_ or {},
                "created_at": _iso(m.created_at), "updated_at": _iso(m.updated_at),
                "state": m.state.value, "app": m.app.name if m.app else None,
                "categories": [c.name for c in m.categories],
                "project_slug": m.project.slug if m.project else None,
                "creator_username": user.user_id,
            }
            gz.write((json.dumps(record) + "\n").encode("utf-8"))
    return buf.getvalue()


@router.post("/export")
async def export_backup(
    req: ExportRequest,
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    user = auth.db_user
    project = None
    if req.project_slug:
        pctx = resolve_project(auth, db, req.project_slug)
        project = pctx.project if pctx else None

    sqlite_payload = _export_sqlite(db=db, user=user, req=req, project=project)
    memories_blob = _export_logical_memories_gz(
        db=db, user=user, app_id=req.app_id,
        from_date=req.from_date, to_date=req.to_date, project=project,
    )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("memories.json", json.dumps(sqlite_payload, indent=2))
        zf.writestr("memories.jsonl.gz", memories_blob)

    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="memories_export_{auth.username}.zip"'},
    )


# ---------------------------------------------------------------------------
# 2. Import (async: SQLite sync + background batch embed)
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_backup(
    file: UploadFile = File(..., description="Zip with memories.json and memories.jsonl.gz"),
    project_slug: Optional[str] = Form(None, description="Target project slug"),
    mode: str = Query("overwrite"),
    auth: AuthenticatedUser = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a zip file.")
    if mode not in {"skip", "overwrite"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be 'skip' or 'overwrite'.")

    user = auth.db_user

    # --- Parse ZIP ---
    content = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            names = zf.namelist()

            def find_member(filename: str) -> Optional[str]:
                for name in names:
                    if name.endswith("/"):
                        continue
                    if name.rsplit("/", 1)[-1] == filename:
                        return name
                return None

            sqlite_member = find_member("memories.json")
            if not sqlite_member:
                raise HTTPException(status_code=400, detail="memories.json missing in zip")
            memories_member = find_member("memories.jsonl.gz")
            sqlite_data = json.loads(zf.read(sqlite_member))
            memories_blob = zf.read(memories_member) if memories_member else None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    export_version = sqlite_data.get("export_meta", {}).get("version", "1")

    # --- Resolve target project ---
    target_project = None
    if project_slug:
        pctx = resolve_project(auth, db, project_slug, min_role=ProjectRole.read_write)
        if pctx:
            target_project = pctx.project
    if not target_project:
        target_project = _get_user_default_project(db, user)
    if not target_project:
        raise HTTPException(400, "No target project available.")

    # --- Ensure default app ---
    default_app = db.query(App).filter(App.owner_id == user.id, App.name == "openmemory").first()
    if not default_app:
        default_app = App(owner_id=user.id, name="openmemory", is_active=True, metadata_={})
        db.add(default_app)
        db.commit()
        db.refresh(default_app)

    def _resolve_app(app_name: Optional[str]) -> App:
        if not app_name:
            return default_app
        existing = db.query(App).filter(App.owner_id == user.id, App.name == app_name).first()
        if existing:
            return existing
        new_app = App(owner_id=user.id, name=app_name, is_active=True, metadata_={})
        db.add(new_app)
        db.commit()
        db.refresh(new_app)
        return new_app

    # --- Import categories ---
    cat_id_map: Dict[str, UUID] = {}
    for c in sqlite_data.get("categories", []):
        cat = db.query(Category).filter(Category.name == c["name"]).first()
        if not cat:
            cat = Category(name=c["name"], description=c.get("description"))
            db.add(cat)
            db.commit()
            db.refresh(cat)
        cat_id_map[c["id"]] = cat.id

    # --- Import memories (SQLite — synchronous, fast) ---
    old_to_new_id: Dict[str, UUID] = {}
    app_for_memory: Dict[str, str] = {}
    imported_count = 0
    skipped_count = 0

    for m in sqlite_data.get("memories", []):
        incoming_id = UUID(m["id"])
        existing = db.query(Memory).filter(Memory.id == incoming_id).first()

        if existing and existing.user_id != user.id:
            target_id = uuid4()
        else:
            target_id = incoming_id
        old_to_new_id[m["id"]] = target_id

        app_name = m.get("app_name") or None
        app_obj = _resolve_app(app_name)
        app_for_memory[m["id"]] = app_obj.name

        mem_project = target_project
        if export_version >= "2" and not project_slug and m.get("project_slug"):
            pctx = resolve_project(auth, db, m["project_slug"], min_role=ProjectRole.read_write)
            if pctx:
                mem_project = pctx.project

        if existing and (existing.user_id == user.id) and mode == "skip":
            skipped_count += 1
            continue

        if existing and (existing.user_id == user.id) and mode == "overwrite":
            existing.app_id = app_obj.id
            existing.project_id = mem_project.id
            existing.content = m.get("content") or ""
            existing.metadata_ = m.get("metadata") or {}
            try:
                existing.state = MemoryState(m.get("state", "active"))
            except Exception:
                existing.state = MemoryState.active
            existing.archived_at = _parse_iso(m.get("archived_at"))
            existing.deleted_at = _parse_iso(m.get("deleted_at"))
            existing.created_at = _parse_iso(m.get("created_at")) or existing.created_at
            existing.updated_at = _parse_iso(m.get("updated_at")) or existing.updated_at
            db.add(existing)
            db.commit()
            imported_count += 1
            continue

        new_mem = Memory(
            id=target_id, user_id=user.id, app_id=app_obj.id, project_id=mem_project.id,
            content=m.get("content") or "", metadata_=m.get("metadata") or {},
            state=MemoryState(m.get("state", "active")) if m.get("state") else MemoryState.active,
            created_at=_parse_iso(m.get("created_at")) or datetime.now(UTC),
            updated_at=_parse_iso(m.get("updated_at")) or datetime.now(UTC),
            archived_at=_parse_iso(m.get("archived_at")),
            deleted_at=_parse_iso(m.get("deleted_at")),
        )
        db.add(new_mem)
        db.commit()
        imported_count += 1

    # --- Import memory_categories ---
    for link in sqlite_data.get("memory_categories", []):
        mid = old_to_new_id.get(link["memory_id"])
        cid = cat_id_map.get(link["category_id"])
        if not (mid and cid):
            continue
        exists = db.execute(
            memory_categories.select().where(
                (memory_categories.c.memory_id == mid) & (memory_categories.c.category_id == cid)
            )
        ).first()
        if not exists:
            db.execute(memory_categories.insert().values(memory_id=mid, category_id=cid))
            db.commit()

    # --- Import status_history ---
    for h in sqlite_data.get("status_history", []):
        hid = UUID(h["id"])
        mem_id = old_to_new_id.get(h["memory_id"], UUID(h["memory_id"]))
        exists = db.query(MemoryStatusHistory).filter(MemoryStatusHistory.id == hid).first()
        if exists and mode == "skip":
            continue
        rec = exists if exists else MemoryStatusHistory(id=hid)
        rec.memory_id = mem_id
        rec.changed_by = user.id
        try:
            rec.old_state = MemoryState(h.get("old_state", "active"))
            rec.new_state = MemoryState(h.get("new_state", "active"))
        except Exception:
            rec.old_state = MemoryState.active
            rec.new_state = MemoryState.active
        rec.changed_at = _parse_iso(h.get("changed_at")) or datetime.now(UTC)
        db.add(rec)
        db.commit()

    # --- Build embed items for background task ---
    embed_items: List[Dict[str, Any]] = []

    def _iter_logical_records():
        if memories_blob:
            gz_buf = io.BytesIO(memories_blob)
            with gzip.GzipFile(fileobj=gz_buf, mode="rb") as gz:
                for raw in gz:
                    yield json.loads(raw.decode("utf-8"))
        else:
            for m in sqlite_data.get("memories", []):
                yield {
                    "id": m["id"], "content": m.get("content"),
                    "metadata": m.get("metadata") or {},
                    "created_at": m.get("created_at"), "updated_at": m.get("updated_at"),
                    "app_name": m.get("app_name"),
                }

    for rec in _iter_logical_records():
        old_id = rec["id"]
        new_id = old_to_new_id.get(old_id, UUID(old_id))
        rec_content = rec.get("content") or ""
        if not rec_content.strip():
            continue

        metadata = rec.get("metadata") or {}
        created_at = rec.get("created_at")
        updated_at = rec.get("updated_at")
        rec_app_name = rec.get("app") or rec.get("app_name") or app_for_memory.get(old_id, "openmemory")

        payload = dict(metadata)
        payload["data"] = rec_content
        if created_at:
            payload["created_at"] = created_at
        if updated_at:
            payload["updated_at"] = updated_at
        payload["user_id"] = auth.username
        payload["project_id"] = str(target_project.id)
        payload["source_app"] = "openmemory"
        payload["mcp_client"] = rec_app_name

        embed_items.append({"id": str(new_id), "content": rec_content, "payload": payload})

    # --- Launch background embedding task ---
    task_id = uuid4().hex[:12]
    _import_tasks[task_id] = {
        "total": len(embed_items),
        "embedded": 0,
        "failed": 0,
        "done": len(embed_items) == 0,
        "type": "import",
        "project_slug": target_project.slug,
        "sqlite_imported": imported_count,
        "sqlite_skipped": skipped_count,
    }

    if embed_items:
        asyncio.create_task(_embed_worker(task_id, embed_items))

    return {
        "task_id": task_id,
        "project_slug": target_project.slug,
        "imported": imported_count,
        "skipped": skipped_count,
        "to_embed": len(embed_items),
    }
