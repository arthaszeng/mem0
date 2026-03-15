"""
MCP Server for Memverse with resilient memory client handling.

This module implements an MCP (Model Context Protocol) server that provides
memory operations for Memverse. The memory client is initialized lazily
to prevent server crashes when external dependencies (like Ollama) are
unavailable. If the memory client cannot be initialized, the server will
continue running with limited functionality and appropriate error messages.

Key features:
- Lazy memory client initialization
- Graceful error handling for unavailable dependencies
- Fallback to database-only mode when vector store is unavailable
- Proper logging for debugging connection issues
- Environment variable parsing for API keys
"""

import asyncio
import contextvars
import datetime
import json
import logging
import uuid

from app.database import SessionLocal
from app.models import Config, Memory, MemoryAccessLog, MemoryState, MemoryStatusHistory
from app.utils.db import get_user_and_app
from app.utils.memory import get_memory_client
from app.utils.categorization import match_domain_by_keywords
from app.utils.domain_registry import add_domain, auto_discover_domains, get_domains
from app.utils.permissions import check_memory_access_permissions
from app.utils.sensitive import sanitize_text
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.routing import APIRouter
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from starlette.types import ASGIApp, Receive, Scope, Send
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sqlalchemy.orm import joinedload

# Load environment variables
load_dotenv()

# Initialize MCP
mcp = FastMCP("memverse-mcp-server")

# ---------------------------------------------------------------------------
# Background memory-write queue: add_memories enqueues and returns immediately;
# a single async worker drains the queue, running the heavy mem0 add() in a
# thread so it never blocks the event loop.
# ---------------------------------------------------------------------------
_memory_task_queue: asyncio.Queue | None = None


def _get_queue() -> asyncio.Queue:
    global _memory_task_queue
    if _memory_task_queue is None:
        _memory_task_queue = asyncio.Queue()
    return _memory_task_queue


def _run_categorization_in_background(memory_id: uuid.UUID, content: str):
    import threading
    from app.models import categorize_memory_background

    t = threading.Thread(
        target=categorize_memory_background,
        args=(memory_id, content),
        daemon=True,
    )
    t.start()


def _run_entity_extraction_in_background(memory_id: uuid.UUID, content: str):
    import threading

    def _extract():
        try:
            from app.utils.entity_extraction import extract_entities
            from app.utils.graph_store import add_entities
            result = extract_entities(content)
            if result.get("entities"):
                add_entities(result["entities"], result.get("relations", []), str(memory_id))
                logging.info("Extracted %d entities from memory %s", len(result["entities"]), memory_id)
        except Exception as e:
            logging.warning("Entity extraction failed for %s: %s", memory_id, e)

    t = threading.Thread(target=_extract, daemon=True)
    t.start()


async def _memory_write_worker():
    """Drain the queue and process memory writes one-by-one in a thread."""
    q = _get_queue()
    while True:
        task = await q.get()
        try:
            if isinstance(task, dict):
                uid = task["uid"]
                client_name = task["client_name"]
                text = task["text"]
                task_project_slug = task.get("project_slug", "")
                task_infer = task.get("infer", True)
                task_instructions = task.get("instructions", "")
                task_expires_at = task.get("expires_at", "")
                task_run_id = task.get("run_id", "")
            else:
                uid, client_name, text, task_project_slug = task[:4]
                task_infer = task[4] if len(task) > 4 else True
                task_instructions = task[5] if len(task) > 5 else ""
                task_expires_at = ""
                task_run_id = ""

            memory_client = get_memory_client_safe()
            if not memory_client:
                logging.warning("Memory worker: client unavailable, dropping task")
                continue

            text = sanitize_text(text)

            db = SessionLocal()
            try:
                user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
                pslug_token = project_slug_var.set(task_project_slug or "")
                try:
                    project_id, _ = _resolve_project(db, user.id)
                finally:
                    project_slug_var.reset(pslug_token)
            finally:
                db.close()

            effective_instructions = task_instructions or ""

            qdrant_meta = {"source_app": "memverse", "mcp_client": client_name, "project_id": project_id}

            saved_prompt = None
            if effective_instructions:
                saved_prompt = memory_client.config.custom_fact_extraction_prompt
                memory_client.config.custom_fact_extraction_prompt = effective_instructions

            try:
                response = await asyncio.to_thread(
                    memory_client.add, text,
                    user_id=uid,
                    metadata=qdrant_meta,
                    infer=task_infer,
                )
            finally:
                if saved_prompt is not None:
                    memory_client.config.custom_fact_extraction_prompt = saved_prompt

            parsed_expires = None
            if task_expires_at:
                try:
                    parsed_expires = datetime.datetime.fromisoformat(task_expires_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    logging.warning("Invalid expires_at value: %s", task_expires_at)

            db = SessionLocal()
            try:
                user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
                memories_to_categorize: list[tuple[uuid.UUID, str]] = []

                if isinstance(response, dict) and "results" in response:
                    for result in response["results"]:
                        memory_id = uuid.UUID(result["id"])
                        memory = db.query(Memory).filter(Memory.id == memory_id).first()

                        if result["event"] == "ADD":
                            if not memory:
                                memory = Memory(
                                    id=memory_id,
                                    user_id=user.id,
                                    app_id=app.id,
                                    project_id=project_id,
                                    content=result["memory"],
                                    state=MemoryState.active,
                                )
                                db.add(memory)
                            else:
                                memory.state = MemoryState.active
                                memory.content = result["memory"]
                                if not memory.project_id:
                                    memory.project_id = project_id

                            if parsed_expires:
                                memory.expires_at = parsed_expires
                            if task_run_id:
                                memory.run_id = task_run_id

                            db.add(MemoryStatusHistory(
                                memory_id=memory_id,
                                changed_by=user.id,
                                old_state=MemoryState.deleted,
                                new_state=MemoryState.active,
                            ))
                            memories_to_categorize.append((memory_id, result["memory"]))

                        elif result["event"] == "UPDATE":
                            if memory:
                                memory.content = result["memory"]
                                memory.updated_at = datetime.datetime.now(datetime.UTC)
                                if not memory.project_id:
                                    memory.project_id = project_id
                            else:
                                memory = Memory(
                                    id=memory_id,
                                    user_id=user.id,
                                    app_id=app.id,
                                    project_id=project_id,
                                    content=result["memory"],
                                    state=MemoryState.active,
                                )
                                db.add(memory)

                            if parsed_expires and memory:
                                memory.expires_at = parsed_expires
                            if task_run_id and memory:
                                memory.run_id = task_run_id

                            memories_to_categorize.append((memory_id, result["memory"]))

                        elif result["event"] == "DELETE":
                            if memory:
                                memory.state = MemoryState.deleted
                                memory.deleted_at = datetime.datetime.now(datetime.UTC)
                                db.add(MemoryStatusHistory(
                                    memory_id=memory_id,
                                    changed_by=user.id,
                                    old_state=MemoryState.active,
                                    new_state=MemoryState.deleted,
                                ))

                    db.commit()

                for mid, content in memories_to_categorize:
                    try:
                        _run_categorization_in_background(mid, content)
                    except Exception as cat_err:
                        logging.warning(f"Categorization schedule failed for {mid}: {cat_err}")
                    try:
                        _run_entity_extraction_in_background(mid, content)
                    except Exception as ge_err:
                        logging.warning(f"Entity extraction schedule failed for {mid}: {ge_err}")

                logging.info(f"Memory worker processed write for user={uid}: {len(response.get('results', []))} results")
            finally:
                db.close()

        except Exception as e:
            logging.exception(f"Memory worker error: {e}")
        finally:
            q.task_done()

# Don't initialize memory client at import time - do it lazily when needed
def get_memory_client_safe():
    """Get memory client with error handling. Returns None if client cannot be initialized."""
    try:
        return get_memory_client()
    except Exception as e:
        logging.warning(f"Failed to get memory client: {e}")
        return None

_insights_profile_cache: dict[str, tuple[dict, "datetime.datetime"]] = {}

# Context variables for user_id, client_name, and project_slug
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id")
client_name_var: contextvars.ContextVar[str] = contextvars.ContextVar("client_name")
project_slug_var: contextvars.ContextVar[str] = contextvars.ContextVar("project_slug", default="")


def _get_user_default_project(db, user_id: int) -> "tuple[str | None, str | None]":
    """Return (project_id, project_slug) for the user's first project membership, or (None, None)."""
    from app.models import ProjectMember, Project
    member = db.query(ProjectMember).filter(ProjectMember.user_id == user_id).first()
    if not member:
        return None, None
    project = db.query(Project).filter(Project.id == member.project_id).first()
    if not project:
        return None, None
    return str(project.id), project.slug


def _resolve_project(db, user_id: int) -> "tuple[str, str]":
    """Resolve project from context var or fall back to user's default project.
    Always returns a valid (project_id, slug). Raises ValueError if none found."""
    from app.models import Project, ProjectMember
    slug = project_slug_var.get("")
    if slug:
        project = db.query(Project).filter(Project.slug == slug).first()
        if project:
            member = db.query(ProjectMember).filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user_id,
            ).first()
            if member:
                return str(project.id), project.slug
            logging.warning(f"User {user_id} not a member of project '{slug}', falling back to default")
    pid, pslug = _get_user_default_project(db, user_id)
    if not pid:
        raise ValueError(f"No project found for user {user_id}")
    return pid, pslug

# Create a router for MCP endpoints
mcp_router = APIRouter(prefix="/memverse-mcp")

# Initialize SSE transport (legacy, kept for backward compat)
sse = SseServerTransport("/memverse-mcp/messages/")

# Streamable HTTP: persistent sessions keyed by mcp-session-id.
# Each session has a long-lived background task running transport.connect() + mcp server.
_streamable_sessions: dict[str, StreamableHTTPServerTransport] = {}
_streamable_tasks: dict[str, asyncio.Task] = {}

@mcp.tool(description="Add a new memory. This method is called everytime the user informs anything about themselves, their preferences, or anything that has any relevant information which can be useful in the future conversation. This can also be called when the user asks you to remember something.")
async def add_memories(
    text: str,
    infer: bool = True,
    instructions: str = "",
    expires_at: str = "",
    run_id: str = "",
) -> str:
    """
    Args:
        text: The content to memorize.
        infer: If True (default), LLM extracts key facts from text. If False, store text as-is.
        instructions: Per-call extraction instructions that override the global prompt for this request only.
        expires_at: ISO 8601 expiration datetime (e.g. "2026-04-01T00:00:00Z"). Memory auto-expires after this time.
        run_id: Identifier for the conversation/session run. Enables session-level memory grouping.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)

    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"
    if not text or not text.strip():
        return "Error: text must not be empty or whitespace-only"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            if not app.is_active:
                return f"Error: App {app.name} is currently paused on Memverse. Cannot create new memories."
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error validating user/app: {e}")
        return f"Error: {e}"

    q = _get_queue()
    pslug = project_slug_var.get("")
    await q.put({
        "uid": uid,
        "client_name": client_name,
        "text": text,
        "project_slug": pslug,
        "infer": infer,
        "instructions": instructions or "",
        "expires_at": expires_at or "",
        "run_id": run_id or "",
    })
    pending = q.qsize()
    return json.dumps({
        "status": "queued",
        "message": f"Memory is being processed in background (queue depth: {pending})",
    })


@mcp.tool(description="Search through stored memories. This method is called EVERYTIME the user asks anything.")
async def search_memory(
    query: str,
    limit: int = 100,
    categories: str = "",
) -> str:
    """
    Args:
        query: The search query string.
        limit: Maximum number of results to return (default 100).
        categories: Comma-separated category names to filter by (e.g. "architecture,bugfix").
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    effective_limit = min(max(limit, 1), 500)
    filter_categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else []

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            project_memories = db.query(Memory).filter(Memory.project_id == project_id).all()
            accessible_memory_ids = [memory.id for memory in project_memories if check_memory_access_permissions(db, memory, app.id)]

            # --- Vector search ---
            qdrant_filters = [FieldCondition(key="project_id", match=MatchValue(value=project_id))]
            query_filter = Filter(must=qdrant_filters)

            def _do_search():
                emb = memory_client.embedding_model.embed(query, "search")
                return memory_client.vector_store.client.query_points(
                    collection_name=memory_client.vector_store.collection_name,
                    query=emb,
                    query_filter=query_filter,
                    limit=effective_limit,
                ).points

            hits = await asyncio.to_thread(_do_search)

            allowed = set(str(mid) for mid in accessible_memory_ids) if accessible_memory_ids else None

            results = []
            seen_ids = set()
            for h in hits:
                id, score, payload = str(h.id), h.score, h.payload or {}
                if allowed and (id is None or id not in allowed):
                    continue
                seen_ids.add(id)
                results.append({
                    "id": id,
                    "memory": payload.get("data"),
                    "hash": payload.get("hash"),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at"),
                    "score": score,
                })

            # --- Domain-augmented search ---
            matched_domain = match_domain_by_keywords(query)
            if matched_domain:
                domain_memories = (
                    db.query(Memory)
                    .filter(
                        Memory.project_id == project_id,
                        Memory.state == MemoryState.active,
                        Memory.metadata_.op("->>")("domain") == matched_domain,
                    )
                    .order_by(Memory.updated_at.desc())
                    .limit(50)
                    .all()
                )
                for dm in domain_memories:
                    mid = str(dm.id)
                    if mid in seen_ids:
                        continue
                    if allowed and mid not in allowed:
                        continue
                    seen_ids.add(mid)
                    results.append({
                        "id": mid,
                        "memory": dm.content,
                        "hash": None,
                        "created_at": dm.created_at.isoformat() if dm.created_at else None,
                        "updated_at": dm.updated_at.isoformat() if dm.updated_at else None,
                        "score": 0.5,
                    })

            # --- Keyword search (SQLite LIKE) ---
            kw_memories = (
                db.query(Memory)
                .filter(
                    Memory.project_id == project_id,
                    Memory.state == MemoryState.active,
                    Memory.content.ilike(f"%{query}%"),
                )
                .order_by(Memory.updated_at.desc())
                .limit(effective_limit)
                .all()
            )
            for km in kw_memories:
                mid = str(km.id)
                if mid in seen_ids:
                    continue
                if allowed and mid not in allowed:
                    continue
                seen_ids.add(mid)
                results.append({
                    "id": mid,
                    "memory": km.content,
                    "hash": None,
                    "created_at": km.created_at.isoformat() if km.created_at else None,
                    "updated_at": km.updated_at.isoformat() if km.updated_at else None,
                    "score": 0.4,
                })

            # --- Graph-enhanced search ---
            try:
                from app.utils.graph_store import search_entities as _graph_search
                graph_entities = _graph_search(query, limit=5)
                for ent in graph_entities:
                    for mid_str in (ent.get("memory_ids") or []):
                        if mid_str in seen_ids:
                            continue
                        if allowed and mid_str not in allowed:
                            continue
                        try:
                            gm = db.query(Memory).filter(Memory.id == uuid.UUID(mid_str), Memory.state == MemoryState.active).first()
                        except (ValueError, AttributeError):
                            gm = None
                        if gm:
                            seen_ids.add(mid_str)
                            results.append({
                                "id": mid_str,
                                "memory": gm.content,
                                "hash": None,
                                "created_at": gm.created_at.isoformat() if gm.created_at else None,
                                "updated_at": gm.updated_at.isoformat() if gm.updated_at else None,
                                "score": 0.6,
                            })
            except Exception as ge:
                logging.debug("Graph-enhanced search skipped: %s", ge)

            # --- Post-filters: categories ---
            if filter_categories:
                filtered = []
                for r in results:
                    try:
                        mem = db.query(Memory).filter(Memory.id == uuid.UUID(r["id"])).first()
                    except (ValueError, AttributeError):
                        mem = None
                    if not mem:
                        filtered.append(r)
                        continue
                    mem_cats = {c.name for c in mem.categories}
                    if not mem_cats.intersection(filter_categories):
                        continue
                    filtered.append(r)
                results = filtered

            results.sort(key=lambda x: x.get("score", 0), reverse=True)

            from app.utils.reranker import rerank, filter_by_relevance
            results = await asyncio.to_thread(rerank, query, results, effective_limit)
            results = await filter_by_relevance(query, results)
            results = results[:effective_limit]

            for r in results:
                if r.get("id"):
                    access_log = MemoryAccessLog(
                        memory_id=uuid.UUID(r["id"]),
                        app_id=app.id,
                        access_type="search",
                        metadata_={
                            "query": query,
                            "score": r.get("score"),
                            "hash": r.get("hash"),
                        },
                    )
                    db.add(access_log)
            db.commit()

            return json.dumps({"results": results}, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error searching memory: {e}"


@mcp.tool(description="List all memories in the user's memory")
async def list_memories() -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            memories = await asyncio.to_thread(memory_client.get_all, user_id=uid)
            filtered_memories = []

            project_memories = db.query(Memory).filter(Memory.project_id == project_id).all()
            accessible_memory_ids = [memory.id for memory in project_memories if check_memory_access_permissions(db, memory, app.id)]
            if isinstance(memories, dict) and 'results' in memories:
                for memory_data in memories['results']:
                    if 'id' in memory_data:
                        memory_id = uuid.UUID(memory_data['id'])
                        if memory_id in accessible_memory_ids:
                            # Create access log entry
                            access_log = MemoryAccessLog(
                                memory_id=memory_id,
                                app_id=app.id,
                                access_type="list",
                                metadata_={
                                    "hash": memory_data.get('hash')
                                }
                            )
                            db.add(access_log)
                            filtered_memories.append(memory_data)
                db.commit()
            else:
                for memory in memories:
                    memory_id = uuid.UUID(memory['id'])
                    memory_obj = db.query(Memory).filter(Memory.id == memory_id).first()
                    if memory_obj and check_memory_access_permissions(db, memory_obj, app.id):
                        # Create access log entry
                        access_log = MemoryAccessLog(
                            memory_id=memory_id,
                            app_id=app.id,
                            access_type="list",
                            metadata_={
                                "hash": memory.get('hash')
                            }
                        )
                        db.add(access_log)
                        filtered_memories.append(memory)
                db.commit()
            return json.dumps(filtered_memories, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error getting memories: {e}")
        return f"Error getting memories: {e}"


@mcp.tool(description="Delete specific memories by their IDs")
async def delete_memories(memory_ids: list[str]) -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            # Convert string IDs to UUIDs and filter accessible ones
            requested_ids = [uuid.UUID(mid) for mid in memory_ids]
            project_memories = db.query(Memory).filter(Memory.project_id == project_id).all()
            accessible_memory_ids = [memory.id for memory in project_memories if check_memory_access_permissions(db, memory, app.id)]

            # Only delete memories that are both requested and accessible
            ids_to_delete = [mid for mid in requested_ids if mid in accessible_memory_ids]

            if not ids_to_delete:
                return "Error: No accessible memories found with provided IDs"

            for memory_id in ids_to_delete:
                try:
                    await asyncio.to_thread(memory_client.delete, str(memory_id))
                except Exception as delete_error:
                    logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

                try:
                    from app.utils.graph_store import remove_entities_for_memory
                    remove_entities_for_memory(str(memory_id))
                except Exception as graph_error:
                    logging.warning(f"Failed to remove entities for memory {memory_id}: {graph_error}")

            now = datetime.datetime.now(datetime.UTC)
            for memory_id in ids_to_delete:
                memory = db.query(Memory).filter(Memory.id == memory_id).first()
                if memory:
                    memory.state = MemoryState.deleted
                    memory.deleted_at = now

                    history = MemoryStatusHistory(
                        memory_id=memory_id,
                        changed_by=user.id,
                        old_state=MemoryState.active,
                        new_state=MemoryState.deleted
                    )
                    db.add(history)

                    access_log = MemoryAccessLog(
                        memory_id=memory_id,
                        app_id=app.id,
                        access_type="delete",
                        metadata_={"operation": "delete_by_id"}
                    )
                    db.add(access_log)

            db.commit()
            return f"Successfully deleted {len(ids_to_delete)} memories"
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error deleting memories: {e}")
        return f"Error deleting memories: {e}"


@mcp.tool(description="Delete all memories in the user's memory")
async def delete_all_memories() -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            project_memories = db.query(Memory).filter(Memory.project_id == project_id).all()
            accessible_memory_ids = [memory.id for memory in project_memories if check_memory_access_permissions(db, memory, app.id)]

            for memory_id in accessible_memory_ids:
                try:
                    await asyncio.to_thread(memory_client.delete, str(memory_id))
                except Exception as delete_error:
                    logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

            try:
                from app.utils.graph_store import clear_all_entities
                clear_all_entities()
            except Exception as graph_error:
                logging.warning(f"Failed to clear Kuzu graph store: {graph_error}")

            now = datetime.datetime.now(datetime.UTC)
            for memory_id in accessible_memory_ids:
                memory = db.query(Memory).filter(Memory.id == memory_id).first()
                # Update memory state
                memory.state = MemoryState.deleted
                memory.deleted_at = now

                # Create history entry
                history = MemoryStatusHistory(
                    memory_id=memory_id,
                    changed_by=user.id,
                    old_state=MemoryState.active,
                    new_state=MemoryState.deleted
                )
                db.add(history)

                # Create access log entry
                access_log = MemoryAccessLog(
                    memory_id=memory_id,
                    app_id=app.id,
                    access_type="delete_all",
                    metadata_={"operation": "bulk_delete"}
                )
                db.add(access_log)

            db.commit()
            return "Successfully deleted all memories"
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error deleting memories: {e}")
        return f"Error deleting memories: {e}"


@mcp.tool(description="Update the content of an existing memory by its ID. Use when the user corrects or refines a previously stored memory.")
async def update_memory(memory_id: str, new_content: str) -> str:
    """
    Args:
        memory_id: The UUID string of the memory to update.
        new_content: The new content to replace the existing memory text.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            mem = db.query(Memory).filter(Memory.id == uuid.UUID(memory_id)).first()
            if not mem:
                return f"Error: Memory {memory_id} not found"
            if mem.user_id != user.id:
                return "Error: Cannot update another user's memory"
            if not check_memory_access_permissions(db, mem, app.id):
                return "Error: Access denied"

            old_content = mem.content
            mem.content = sanitize_text(new_content)
            mem.updated_at = datetime.datetime.now(datetime.UTC)

            db.add(MemoryAccessLog(
                memory_id=mem.id, app_id=app.id,
                access_type="update",
                metadata_={"old_content": old_content[:200]},
            ))
            db.commit()

            try:
                _run_categorization_in_background(mem.id, mem.content)
                _run_entity_extraction_in_background(mem.id, mem.content)
            except Exception:
                pass

            return json.dumps({"status": "updated", "memory_id": memory_id})
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error updating memory: {e}"


@mcp.tool(description="Archive memories by their IDs. Archived memories are hidden from search but can be restored later.")
async def archive_memories(memory_ids: list[str]) -> str:
    """
    Args:
        memory_ids: List of memory UUID strings to archive.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)
            archived = 0
            for mid_str in memory_ids:
                try:
                    mid = uuid.UUID(mid_str)
                except ValueError:
                    continue
                mem = db.query(Memory).filter(Memory.id == mid, Memory.project_id == project_id).first()
                if mem and mem.state == MemoryState.active:
                    mem.state = MemoryState.archived
                    mem.archived_at = datetime.datetime.now(datetime.UTC)
                    db.add(MemoryStatusHistory(
                        memory_id=mid, changed_by=user.id,
                        old_state=MemoryState.active, new_state=MemoryState.archived,
                    ))
                    archived += 1
            db.commit()
            return f"Archived {archived} memories"
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error archiving memories: {e}"


@mcp.tool(description="Restore previously archived memories back to active state.")
async def restore_memories(memory_ids: list[str]) -> str:
    """
    Args:
        memory_ids: List of memory UUID strings to restore.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)
            restored = 0
            for mid_str in memory_ids:
                try:
                    mid = uuid.UUID(mid_str)
                except ValueError:
                    continue
                mem = db.query(Memory).filter(Memory.id == mid, Memory.project_id == project_id).first()
                if mem and mem.state == MemoryState.archived:
                    mem.state = MemoryState.active
                    mem.archived_at = None
                    db.add(MemoryStatusHistory(
                        memory_id=mid, changed_by=user.id,
                        old_state=MemoryState.archived, new_state=MemoryState.active,
                    ))
                    restored += 1
            db.commit()
            return f"Restored {restored} memories"
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error restoring memories: {e}"


# ---------------------------------------------------------------------------
# Domain management tools (does NOT change existing tool interfaces)
# ---------------------------------------------------------------------------

@mcp.tool(description="List all registered memory domains. Use this to see what project/domain categories are available for memory classification.")
async def list_domains() -> str:
    try:
        domains = get_domains()
        lines = [f"Registered domains ({len(domains)}):"]
        for name, info in domains.items():
            aliases_str = ", ".join(info.get("aliases", [])[:5])
            kw_str = ", ".join(info.get("keywords", [])[:5])
            lines.append(f"  - {name} ({info.get('display', '')})")
            lines.append(f"    aliases: {aliases_str}")
            lines.append(f"    keywords: {kw_str}...")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing domains: {e}"


@mcp.tool(description="Add or update a memory domain. Provide a name (like 'ProjectX/Feature'), display name (Chinese), comma-separated aliases, and comma-separated keywords.")
async def manage_domain(name: str, display: str, aliases: str, keywords: str) -> str:
    try:
        alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        add_domain(name=name, display=display, aliases=alias_list, keywords=kw_list)
        return f"Domain '{name}' ({display}) saved with {len(alias_list)} aliases and {len(kw_list)} keywords. Cache invalidated."
    except Exception as e:
        return f"Error managing domain: {e}"


@mcp.tool(description="Show domain candidates discovered automatically from memories. These are domains the LLM suggested that aren't in the registry yet.")
async def show_domain_candidates() -> str:
    try:
        suggestions = auto_discover_domains()
        if not suggestions:
            return "No domain candidates found yet. Candidates are recorded when the LLM suggests unknown domains during memory classification."
        lines = [f"Domain candidates ({len(suggestions)}):"]
        for s in suggestions:
            status = "AUTO-PROMOTABLE" if s["auto_promotable"] else "needs more data"
            lines.append(f"  - '{s['candidate']}' (count={s['count']}, {status})")
            if s.get("snippets"):
                lines.append(f"    sample: {s['snippets'][0][:100]}...")
        return "\n".join(lines)
    except Exception as e:
        return f"Error showing candidates: {e}"


@mcp.tool(description="Run a complex multi-step task using the LangGraph AI agent. The agent has access to memory tools and can search/store memories while executing. Use for tasks that need reasoning across multiple steps.")
async def run_agent_task(prompt: str) -> str:
    """Delegate a task to the LangGraph agent service."""
    import os
    import httpx

    agent_url = os.getenv("LANGGRAPH_AGENT_URL", "http://127.0.0.1:8766")
    uid = user_id_var.get(None)
    if not uid:
        return "Error: user_id not available in current session"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{agent_url}/agent/run",
                json={"prompt": prompt, "user_id": uid},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", str(data))
    except httpx.ConnectError:
        return "LangGraph agent service is not running. Start it first."
    except Exception as e:
        return f"Agent error: {e}"


def _get_global_custom_instructions(db) -> str:
    db_config = db.query(Config).filter(Config.key == "main").first()
    if db_config and isinstance(db_config.value, dict):
        ci = db_config.value.get("openmemory", {}).get("custom_instructions")
        if ci:
            return ci
    from app.utils.prompts import build_fact_extraction_prompt
    return build_fact_extraction_prompt()


@mcp.tool(description="Find and consolidate similar/duplicate memories. Scans recent memories, identifies near-duplicates, and merges them into concise consolidated entries. Call periodically to keep memory clean.")
async def consolidate_memories(dry_run: bool = True) -> str:
    """
    Args:
        dry_run: If True (default), show what would be consolidated without changing anything. Set False to actually merge.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)
            memories = (
                db.query(Memory)
                .filter(Memory.project_id == project_id, Memory.state == MemoryState.active)
                .order_by(Memory.updated_at.desc())
                .limit(200)
                .all()
            )

            from difflib import SequenceMatcher
            groups = []
            used = set()
            for i, m1 in enumerate(memories):
                if m1.id in used:
                    continue
                group = [{"id": str(m1.id), "content": m1.content}]
                used.add(m1.id)
                for m2 in memories[i+1:]:
                    if m2.id in used:
                        continue
                    ratio = SequenceMatcher(None, m1.content.lower(), m2.content.lower()).ratio()
                    if ratio > 0.6:
                        group.append({"id": str(m2.id), "content": m2.content})
                        used.add(m2.id)
                if len(group) > 1:
                    groups.append(group)

            if not groups:
                return json.dumps({"status": "clean", "message": "No similar memories found to consolidate"})

            results = []
            for group in groups:
                from app.utils.intelligence import consolidate_memories as _consolidate
                consolidated = await asyncio.to_thread(_consolidate, group)
                entry = {
                    "original_ids": [m["id"] for m in group],
                    "original_count": len(group),
                    "consolidated": consolidated or group[0]["content"],
                }
                results.append(entry)

                if not dry_run and consolidated:
                    keeper = db.query(Memory).filter(Memory.id == uuid.UUID(group[0]["id"])).first()
                    if keeper:
                        keeper.content = consolidated
                        keeper.updated_at = datetime.datetime.now(datetime.UTC)
                    for m in group[1:]:
                        dup = db.query(Memory).filter(Memory.id == uuid.UUID(m["id"])).first()
                        if dup:
                            dup.state = MemoryState.archived
                            dup.archived_at = datetime.datetime.now(datetime.UTC)

            if not dry_run:
                db.commit()

            return json.dumps({
                "status": "dry_run" if dry_run else "consolidated",
                "groups": results,
                "total_groups": len(results),
            }, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error consolidating: {e}"


@mcp.tool(description="Check if a text contradicts any existing memories. Useful before adding a memory that might conflict with stored knowledge.")
async def check_contradiction(text: str) -> str:
    """
    Args:
        text: The new memory text to check for contradictions against existing memories.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)
            recent = (
                db.query(Memory)
                .filter(Memory.project_id == project_id, Memory.state == MemoryState.active)
                .order_by(Memory.updated_at.desc())
                .limit(50)
                .all()
            )
            existing = [{"id": str(m.id), "content": m.content} for m in recent]

            from app.utils.intelligence import detect_contradiction
            result = await asyncio.to_thread(detect_contradiction, text, existing)
            return json.dumps(result, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error checking contradiction: {e}"


@mcp.tool(description="Export a structured summary of the user's memories grouped by category. Useful for building user profiles or reviewing stored knowledge.")
async def export_memories(format: str = "json") -> str:
    """
    Args:
        format: Output format — "json" (structured) or "text" (human-readable summary).
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)
            memories = (
                db.query(Memory)
                .filter(Memory.project_id == project_id, Memory.state == MemoryState.active)
                .order_by(Memory.updated_at.desc())
                .limit(500)
                .all()
            )

            by_category = {}
            uncategorized = []
            for mem in memories:
                cats = [c.name for c in mem.categories]
                entry = {
                    "id": str(mem.id),
                    "content": mem.content,
                    "created_at": mem.created_at.isoformat() if mem.created_at else None,
                }
                if cats:
                    for cat in cats:
                        by_category.setdefault(cat, []).append(entry)
                else:
                    uncategorized.append(entry)

            if format == "text":
                lines = [f"Memory Export for {uid} ({len(memories)} memories)\n"]
                for cat, items in sorted(by_category.items()):
                    lines.append(f"\n## {cat} ({len(items)})")
                    for item in items:
                        lines.append(f"- {item['content']}")
                if uncategorized:
                    lines.append(f"\n## Uncategorized ({len(uncategorized)})")
                    for item in uncategorized:
                        lines.append(f"- {item['content']}")
                return "\n".join(lines)

            return json.dumps({
                "user_id": uid,
                "total": len(memories),
                "categories": by_category,
                "uncategorized": uncategorized,
            }, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error exporting memories: {e}"


def _mcp_get_allowed_memory_ids() -> set[str]:
    """Return memory IDs accessible to the current MCP user (scoped by project)."""
    uid = user_id_var.get(None)
    if not uid:
        return set()
    db = SessionLocal()
    try:
        user, _ = get_user_and_app(db, user_id=uid, app_id=client_name_var.get("unknown"))
        project_id, _ = _resolve_project(db, user.id)
        rows = db.query(Memory.id).filter(Memory.project_id == project_id, Memory.state == MemoryState.active).all()
        return {str(r[0]) for r in rows}
    except Exception:
        return set()
    finally:
        db.close()


def _filter_entities_by_allowed(entities: list[dict], allowed: set[str]) -> list[dict]:
    return [e for e in entities if any(mid in allowed for mid in (e.get("memory_ids") or []))]


@mcp.tool(description="Search the knowledge graph for entities (people, projects, technologies) and their relationships. Use when the user asks about connections between concepts or wants to explore related knowledge.")
async def search_entities(query: str, limit: int = 20) -> str:
    """
    Args:
        query: Entity name or substring to search for.
        limit: Maximum number of entities to return.
    """
    try:
        from app.utils.graph_store import search_entities as _search
        results = await asyncio.to_thread(_search, query, limit * 3)
        allowed = _mcp_get_allowed_memory_ids()
        filtered = _filter_entities_by_allowed(results, allowed)[:limit]
        for e in filtered:
            e.pop("memory_ids", None)
        if not filtered:
            return json.dumps({"entities": [], "message": "No matching entities found"})
        return json.dumps({"entities": filtered}, indent=2)
    except Exception as e:
        logging.exception(e)
        return f"Error searching entities: {e}"


@mcp.tool(description="List all entities in the knowledge graph. Shows people, projects, technologies and other concepts extracted from memories.")
async def list_graph_entities(limit: int = 100) -> str:
    """
    Args:
        limit: Maximum number of entities to return.
    """
    try:
        from app.utils.graph_store import list_entities as _list
        results = await asyncio.to_thread(_list, limit * 3)
        allowed = _mcp_get_allowed_memory_ids()
        filtered = _filter_entities_by_allowed(results, allowed)[:limit]
        for e in filtered:
            e.pop("memory_ids", None)
        return json.dumps({"entities": filtered, "total": len(filtered)}, indent=2)
    except Exception as e:
        logging.exception(e)
        return f"Error listing entities: {e}"


@mcp.tool(description="Get intelligent insights about stored memories — user profile summary, trending topics, and knowledge coverage. Use when the user asks about their memory patterns or wants an overview.")
async def get_insights(refresh: bool = False) -> str:
    """
    Args:
        refresh: If True, regenerate the user profile from LLM. Default False uses cached profile.
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        return "Error: user_id not provided"
    if not client_name:
        return "Error: client_name not provided"

    try:
        db = SessionLocal()
        try:
            user, _ = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            base_filters = [
                Memory.state != MemoryState.deleted,
                Memory.state != MemoryState.archived,
                Memory.project_id == project_id,
            ]

            memories = (
                db.query(Memory)
                .filter(*base_filters)
                .options(joinedload(Memory.categories))
                .order_by(Memory.created_at.desc())
                .all()
            )

            memory_dicts = []
            cat_counts = {}
            domain_counts = {}
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

            from app.utils.insights import (
                compute_knowledge_coverage,
                compute_topic_trends,
                generate_user_profile,
            )

            topic_trends = compute_topic_trends(memory_dicts, days=30)
            categories_list = [{"name": k, "count": v} for k, v in cat_counts.items()]
            domains_list = [{"name": k, "count": v} for k, v in domain_counts.items()]
            knowledge_coverage = compute_knowledge_coverage(
                categories_list, domains_list, total_memories=len(memories)
            )

            cache_key = f"{uid}:{project_id or ''}"
            user_profile = None
            cache_ttl = datetime.timedelta(hours=1)
            now = datetime.datetime.now(datetime.UTC)
            if not refresh and cache_key in _insights_profile_cache:
                cached_profile, cached_at = _insights_profile_cache[cache_key]
                if (now - cached_at) < cache_ttl:
                    user_profile = cached_profile
            if user_profile is None and memory_dicts:
                try:
                    user_profile = await generate_user_profile(memory_dicts)
                    if user_profile:
                        _insights_profile_cache[cache_key] = (user_profile, now)
                except Exception as e:
                    logging.warning("get_insights profile generation failed: %s", e)

            return json.dumps({
                "user_profile": user_profile,
                "topic_trends": topic_trends,
                "knowledge_coverage": knowledge_coverage,
            }, indent=2)
        finally:
            db.close()
    except Exception as e:
        logging.exception(e)
        return f"Error getting insights: {e}"


def _read_gateway_user(request: Request) -> str:
    """Read username from nginx gateway headers; fall back to path param for backward compat."""
    username = request.headers.get("X-Auth-Username")
    if username:
        return username
    uid = request.path_params.get("user_id")
    if uid:
        return uid
    return ""


# ---------------------------------------------------------------------------
# ASGI middleware — prevents "response already completed" RuntimeError
# ---------------------------------------------------------------------------
#
# MCP transports (SSE / Streamable HTTP) write HTTP responses directly through
# the raw ASGI ``send`` callable.  FastAPI then tries to send its own auto-
# generated response, causing a duplicate ``http.response.start``.
#
# Wrapping ``request._send`` inside the handler does NOT help because FastAPI's
# routing layer holds a *separate* reference to ``send`` from the middleware
# chain.  The fix must be applied at the middleware level so that ALL downstream
# callers — transport AND FastAPI — share the same guarded ``send``.

class _MCPSafeSendMiddleware:
    """Drop duplicate ASGI response messages on MCP transport endpoints."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/memverse-mcp/"):
            await self.app(scope, receive, send)
            return

        completed = False

        async def safe_send(message: dict) -> None:
            nonlocal completed
            if completed:
                return
            if message.get("type") == "http.response.body" and not message.get("more_body", False):
                completed = True
            await send(message)

        await self.app(scope, receive, safe_send)


# ---------------------------------------------------------------------------
# SSE transport (legacy) — kept for backward compatibility with older clients
# ---------------------------------------------------------------------------

async def _run_sse_session(request: Request, uid: str, client_name: str, pslug: str = ""):
    """Common SSE session handler that sets all context vars."""
    user_token = user_id_var.set(uid)
    client_token = client_name_var.set(client_name)
    project_token = project_slug_var.set(pslug)
    try:
        async with sse.connect_sse(request.scope, request.receive, request._send) as (r, w):
            await mcp._mcp_server.run(r, w, mcp._mcp_server.create_initialization_options())
    finally:
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)
        project_slug_var.reset(project_token)


# ---------------------------------------------------------------------------
# Streamable HTTP transport — preferred by Cursor and newer MCP clients.
# On the same paths as SSE (POST=streamable, GET=SSE for backward compat).
# ---------------------------------------------------------------------------

async def _streamable_session_lifecycle(
    transport: StreamableHTTPServerTransport,
    uid: str, client_name: str, pslug: str,
    ready: asyncio.Event,
):
    """Long-lived background task: keeps transport connected and MCP server running."""
    user_id_var.set(uid)
    client_name_var.set(client_name)
    project_slug_var.set(pslug)
    try:
        async with transport.connect() as (r, w):
            ready.set()
            await mcp._mcp_server.run(r, w, mcp._mcp_server.create_initialization_options())
    except asyncio.CancelledError:
        pass
    finally:
        sid = transport.mcp_session_id
        if sid:
            _streamable_sessions.pop(sid, None)
            _streamable_tasks.pop(sid, None)


async def _run_streamable_session(request: Request, uid: str, client_name: str, pslug: str = ""):
    """Handle a single Streamable HTTP request, creating or reusing a persistent session."""
    session_id = request.headers.get("mcp-session-id")

    if session_id and session_id in _streamable_sessions:
        transport = _streamable_sessions[session_id]
        await transport.handle_request(request.scope, request.receive, request._send)
        return

    transport = StreamableHTTPServerTransport(mcp_session_id=str(uuid.uuid4()))
    ready = asyncio.Event()
    task = asyncio.create_task(
        _streamable_session_lifecycle(transport, uid, client_name, pslug, ready)
    )
    await ready.wait()

    sid = transport.mcp_session_id
    if sid:
        _streamable_sessions[sid] = transport
        _streamable_tasks[sid] = task

    await transport.handle_request(request.scope, request.receive, request._send)

    if transport.mcp_session_id and transport.mcp_session_id not in _streamable_sessions:
        _streamable_sessions[transport.mcp_session_id] = transport
        _streamable_tasks[transport.mcp_session_id] = task


def _extract_params(request: Request):
    """Extract uid, client_name, project_slug from request path params + headers."""
    uid = _read_gateway_user(request)
    client_name = request.path_params.get("client_name", "")
    pslug = request.path_params.get("project_slug", "")
    return uid, client_name, pslug


async def _handle_mcp_endpoint(request: Request):
    """Unified handler: POST → Streamable HTTP, GET → SSE (legacy)."""
    uid, client_name, pslug = _extract_params(request)
    if request.method == "POST":
        await _run_streamable_session(request, uid, client_name, pslug)
    else:
        await _run_sse_session(request, uid, client_name, pslug)


# --- Project-scoped routes ---

@mcp_router.api_route("/p/{project_slug}/{client_name}/sse", methods=["GET", "POST", "DELETE"])
async def handle_mcp_project(request: Request):
    await _handle_mcp_endpoint(request)

@mcp_router.api_route("/p/{project_slug}/{client_name}/sse/{user_id}", methods=["GET", "POST", "DELETE"])
async def handle_mcp_project_compat(request: Request):
    await _handle_mcp_endpoint(request)

# --- Legacy routes (no project context) ---

@mcp_router.api_route("/{client_name}/sse", methods=["GET", "POST", "DELETE"])
async def handle_mcp_new(request: Request):
    await _handle_mcp_endpoint(request)

@mcp_router.api_route("/{client_name}/sse/{user_id}", methods=["GET", "POST", "DELETE"])
async def handle_mcp_compat(request: Request):
    await _handle_mcp_endpoint(request)

# --- SSE message endpoints (legacy POST for SSE transport) ---

@mcp_router.post("/messages/")
async def handle_messages_root(request: Request):
    return await _handle_sse_post_message(request)

@mcp_router.post("/{client_name}/sse/{user_id}/messages/")
async def handle_messages_compat(request: Request):
    return await _handle_sse_post_message(request)


async def _handle_sse_post_message(request: Request):
    """Handle POST messages for legacy SSE transport."""
    body = await request.body()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        return {}

    await sse.handle_post_message(request.scope, receive, send)
    return {"status": "ok"}

def setup_mcp_server(app: FastAPI):
    """Setup MCP server with the FastAPI application"""
    mcp._mcp_server.name = "memverse-mcp-server"

    from app.mcp_prompts import register_prompts
    register_prompts(mcp, user_id_var, client_name_var, project_slug_var)

    @app.on_event("startup")
    async def _start_memory_worker():
        asyncio.create_task(_memory_write_worker())
        logging.info("Memory write worker started")

        from app.utils.ttl_cleanup import ttl_cleanup_loop
        asyncio.create_task(ttl_cleanup_loop())
        logging.info("TTL cleanup loop started")

        from app.utils.archive_policy import archive_policy_loop
        asyncio.create_task(archive_policy_loop())
        logging.info("Archive policy loop started")

    app.add_middleware(_MCPSafeSendMiddleware)
    app.include_router(mcp_router)
