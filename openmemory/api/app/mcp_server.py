"""
MCP Server for OpenMemory with resilient memory client handling.

This module implements an MCP (Model Context Protocol) server that provides
memory operations for OpenMemory. The memory client is initialized lazily
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
from app.models import Memory, MemoryAccessLog, MemoryState, MemoryStatusHistory
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
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Load environment variables
load_dotenv()

# Initialize MCP
mcp = FastMCP("mem0-mcp-server")

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
                task_memory_type = task.get("memory_type", "")
                task_agent_id = task.get("agent_id", "")
                task_run_id = task.get("run_id", "")
            else:
                uid, client_name, text, task_project_slug = task[:4]
                task_infer = task[4] if len(task) > 4 else True
                task_instructions = task[5] if len(task) > 5 else ""
                task_expires_at = ""
                task_memory_type = ""
                task_agent_id = ""
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

            qdrant_meta = {"source_app": "openmemory", "mcp_client": client_name}
            if project_id:
                qdrant_meta["project_id"] = project_id

            saved_prompt = None
            if task_instructions:
                saved_prompt = memory_client.config.custom_fact_extraction_prompt
                memory_client.config.custom_fact_extraction_prompt = task_instructions

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
                                if project_id and not memory.project_id:
                                    memory.project_id = project_id

                            if parsed_expires:
                                memory.expires_at = parsed_expires
                            if task_memory_type:
                                memory.memory_type = task_memory_type

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
                                if project_id and not memory.project_id:
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
                            if task_memory_type and memory:
                                memory.memory_type = task_memory_type
                            if task_agent_id and memory:
                                memory.agent_id = task_agent_id
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


def _resolve_project(db, user_id: int) -> "tuple[str | None, str | None]":
    """Resolve project from context var or fall back to user's default project."""
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
    return _get_user_default_project(db, user_id)

# Create a router for MCP endpoints
mcp_router = APIRouter(prefix="/memory-mcp")

# Initialize SSE transport
sse = SseServerTransport("/memory-mcp/messages/")

@mcp.tool(description="Add a new memory. This method is called everytime the user informs anything about themselves, their preferences, or anything that has any relevant information which can be useful in the future conversation. This can also be called when the user asks you to remember something.")
async def add_memories(
    text: str,
    infer: bool = True,
    instructions: str = "",
    expires_at: str = "",
    memory_type: str = "",
    agent_id: str = "",
    run_id: str = "",
) -> str:
    """
    Args:
        text: The content to memorize.
        infer: If True (default), LLM extracts key facts from text. If False, store text as-is.
        instructions: Per-call extraction instructions that override the global prompt for this request only.
        expires_at: ISO 8601 expiration datetime (e.g. "2026-04-01T00:00:00Z"). Memory auto-expires after this time.
        memory_type: One of "fact", "preference", "session", "episodic". Helps with retrieval filtering.
        agent_id: Identifier for the AI agent role (e.g. "cursor", "copilot", "chatgpt"). Enables per-agent memory scoping.
        run_id: Identifier for the conversation/session run. Enables session-level memory grouping.
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
            if not app.is_active:
                return f"Error: App {app.name} is currently paused on OpenMemory. Cannot create new memories."
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
        "memory_type": memory_type or "",
        "agent_id": agent_id or "",
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
    memory_type: str = "",
    agent_id: str = "",
) -> str:
    """
    Args:
        query: The search query string.
        limit: Maximum number of results to return (default 100).
        categories: Comma-separated category names to filter by (e.g. "architecture,bugfix").
        memory_type: Filter by memory type: "fact", "preference", "session", or "episodic".
        agent_id: Filter by AI agent role (e.g. "cursor", "copilot"). Empty = all agents.
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
    filter_memory_type = memory_type.strip() if memory_type else ""
    filter_agent_id = agent_id.strip() if agent_id else ""

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            project_id, _ = _resolve_project(db, user.id)

            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]

            # --- Vector search ---
            qdrant_filters = [FieldCondition(key="user_id", match=MatchValue(value=uid))]
            if project_id:
                qdrant_filters.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))
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
                        Memory.user_id == user.id,
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
            kw_q = (
                db.query(Memory)
                .filter(
                    Memory.user_id == user.id,
                    Memory.state == MemoryState.active,
                    Memory.content.ilike(f"%{query}%"),
                )
            )
            if project_id:
                kw_q = kw_q.filter(Memory.project_id == project_id)
            kw_memories = kw_q.order_by(Memory.updated_at.desc()).limit(effective_limit).all()
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

            # --- Post-filters: categories, memory_type, agent_id ---
            if filter_categories or filter_memory_type or filter_agent_id:
                filtered = []
                for r in results:
                    try:
                        mem = db.query(Memory).filter(Memory.id == uuid.UUID(r["id"])).first()
                    except (ValueError, AttributeError):
                        mem = None
                    if not mem:
                        filtered.append(r)
                        continue
                    if filter_memory_type and mem.memory_type != filter_memory_type:
                        continue
                    if filter_agent_id and mem.agent_id != filter_agent_id:
                        continue
                    if filter_categories:
                        mem_cats = {c.name for c in mem.categories}
                        if not mem_cats.intersection(filter_categories):
                            continue
                    filtered.append(r)
                results = filtered

            # Sort by score descending, truncate to limit
            results.sort(key=lambda x: x.get("score", 0), reverse=True)
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

            mem_q = db.query(Memory).filter(Memory.user_id == user.id)
            if project_id:
                mem_q = mem_q.filter(Memory.project_id == project_id)
            user_memories = mem_q.all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]
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

            # Convert string IDs to UUIDs and filter accessible ones
            requested_ids = [uuid.UUID(mid) for mid in memory_ids]
            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]

            # Only delete memories that are both requested and accessible
            ids_to_delete = [mid for mid in requested_ids if mid in accessible_memory_ids]

            if not ids_to_delete:
                return "Error: No accessible memories found with provided IDs"

            for memory_id in ids_to_delete:
                try:
                    await asyncio.to_thread(memory_client.delete, str(memory_id))
                except Exception as delete_error:
                    logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

            # Update each memory's state and create history entries
            now = datetime.datetime.now(datetime.UTC)
            for memory_id in ids_to_delete:
                memory = db.query(Memory).filter(Memory.id == memory_id).first()
                if memory:
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

            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]

            for memory_id in accessible_memory_ids:
                try:
                    await asyncio.to_thread(memory_client.delete, str(memory_id))
                except Exception as delete_error:
                    logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

            # Update each memory's state and create history entries
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
            archived = 0
            for mid_str in memory_ids:
                try:
                    mid = uuid.UUID(mid_str)
                except ValueError:
                    continue
                mem = db.query(Memory).filter(Memory.id == mid, Memory.user_id == user.id).first()
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
            restored = 0
            for mid_str in memory_ids:
                try:
                    mid = uuid.UUID(mid_str)
                except ValueError:
                    continue
                mem = db.query(Memory).filter(Memory.id == mid, Memory.user_id == user.id).first()
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
            memories = (
                db.query(Memory)
                .filter(Memory.user_id == user.id, Memory.state == MemoryState.active)
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
                    "memory_type": mem.memory_type,
                    "agent_id": mem.agent_id,
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


@mcp.tool(description="Search the knowledge graph for entities (people, projects, technologies) and their relationships. Use when the user asks about connections between concepts or wants to explore related knowledge.")
async def search_entities(query: str, limit: int = 20) -> str:
    """
    Args:
        query: Entity name or substring to search for.
        limit: Maximum number of entities to return.
    """
    try:
        from app.utils.graph_store import search_entities as _search
        results = await asyncio.to_thread(_search, query, limit)
        if not results:
            return json.dumps({"entities": [], "message": "No matching entities found"})
        return json.dumps({"entities": results}, indent=2)
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
        results = await asyncio.to_thread(_list, limit)
        return json.dumps({"entities": results, "total": len(results)}, indent=2)
    except Exception as e:
        logging.exception(e)
        return f"Error listing entities: {e}"


def _read_gateway_user(request: Request) -> str:
    """Read username from nginx gateway headers; fall back to path param for backward compat."""
    username = request.headers.get("X-Auth-Username")
    if username:
        return username
    uid = request.path_params.get("user_id")
    if uid:
        return uid
    return ""


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


# --- Project-scoped SSE routes (preferred) ---

@mcp_router.get("/p/{project_slug}/{client_name}/sse")
async def handle_sse_project(request: Request):
    """Project-scoped SSE endpoint – user identity from gateway headers."""
    uid = _read_gateway_user(request)
    client_name = request.path_params.get("client_name", "")
    pslug = request.path_params.get("project_slug", "")
    await _run_sse_session(request, uid, client_name, pslug)


@mcp_router.get("/p/{project_slug}/{client_name}/sse/{user_id}")
async def handle_sse_project_compat(request: Request):
    """Project-scoped SSE endpoint with user_id in path (backward compat)."""
    uid = _read_gateway_user(request)
    client_name = request.path_params.get("client_name", "")
    pslug = request.path_params.get("project_slug", "")
    await _run_sse_session(request, uid, client_name, pslug)


# --- Legacy routes (no project context, fall back to default project) ---

@mcp_router.get("/{client_name}/sse")
async def handle_sse_new(request: Request):
    """SSE endpoint – user identity from gateway headers, no project context."""
    uid = _read_gateway_user(request)
    client_name = request.path_params.get("client_name", "")
    await _run_sse_session(request, uid, client_name)


@mcp_router.get("/{client_name}/sse/{user_id}")
async def handle_sse_compat(request: Request):
    """Backward-compatible SSE endpoint with user_id in path."""
    uid = _read_gateway_user(request)
    client_name = request.path_params.get("client_name", "")
    await _run_sse_session(request, uid, client_name)


@mcp_router.post("/messages/")
async def handle_messages_root(request: Request):
    return await _handle_post_message(request)


@mcp_router.post("/{client_name}/sse/{user_id}/messages/")
async def handle_messages_compat(request: Request):
    return await _handle_post_message(request)


async def _handle_post_message(request: Request):
    """Handle POST messages for SSE."""
    body = await request.body()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        return {}

    await sse.handle_post_message(request.scope, receive, send)
    return {"status": "ok"}

def setup_mcp_server(app: FastAPI):
    """Setup MCP server with the FastAPI application"""
    mcp._mcp_server.name = "mem0-mcp-server"

    from app.mcp_prompts import register_prompts
    register_prompts(mcp, user_id_var, client_name_var)

    @app.on_event("startup")
    async def _start_memory_worker():
        asyncio.create_task(_memory_write_worker())
        logging.info("Memory write worker started")

        from app.utils.ttl_cleanup import ttl_cleanup_loop
        asyncio.create_task(ttl_cleanup_loop())
        logging.info("TTL cleanup loop started")

    app.include_router(mcp_router)
