"""Kuzu-based graph store for entity-relationship memory.

Provides an embedded graph database (zero external services, like SQLite)
for storing entities and their relationships extracted from memories.
Uses Kuzu's native cursor API — no pandas dependency.
"""
import logging
import os
import threading
from typing import List

logger = logging.getLogger(__name__)

_db = None
_conn = None
_lock = threading.Lock()

GRAPH_DB_PATH = os.environ.get("GRAPH_DB_PATH", "/data/openmemory_graph")
if not os.path.isdir(os.path.dirname(GRAPH_DB_PATH)) and not os.path.isdir("/data"):
    GRAPH_DB_PATH = "./openmemory_graph"


def _get_connection():
    global _db, _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:
            return _conn
        try:
            import kuzu
            _db = kuzu.Database(GRAPH_DB_PATH)
            _conn = kuzu.Connection(_db)
            _init_schema(_conn)
            logger.info("Kuzu graph store initialized at %s", GRAPH_DB_PATH)
            return _conn
        except ImportError:
            logger.warning("kuzu not installed — graph memory disabled")
            return None
        except Exception as e:
            logger.error("Failed to initialize Kuzu: %s", e)
            return None


def _init_schema(conn):
    try:
        conn.execute("CREATE NODE TABLE IF NOT EXISTS Entity(name STRING, type STRING, memory_ids STRING[], PRIMARY KEY(name))")
        conn.execute("CREATE REL TABLE IF NOT EXISTS RELATES_TO(FROM Entity TO Entity, relation STRING, memory_id STRING)")
    except Exception as e:
        logger.error("Failed to create Kuzu schema: %s", e)


def _query_rows(conn, cypher: str) -> List[list]:
    """Execute a Cypher query and return all rows as lists."""
    result = conn.execute(cypher)
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    return rows


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def add_entities(entities: List[dict], relations: List[dict], memory_id: str):
    """Add entities and relations extracted from a memory."""
    conn = _get_connection()
    if not conn:
        return

    try:
        for ent in entities:
            name = _escape(ent["name"])
            etype = _escape(ent.get("type", "unknown"))
            mid = _escape(memory_id)
            existing = _query_rows(conn, f"MATCH (e:Entity) WHERE e.name = '{name}' RETURN e.memory_ids")
            if not existing:
                conn.execute(f"CREATE (e:Entity {{name: '{name}', type: '{etype}', memory_ids: ['{mid}']}})")
            else:
                conn.execute(f"MATCH (e:Entity) WHERE e.name = '{name}' SET e.memory_ids = list_append(e.memory_ids, '{mid}')")

        for rel in relations:
            src = _escape(rel["source"])
            tgt = _escape(rel["target"])
            rtype = _escape(rel.get("relation", "related_to"))
            mid = _escape(memory_id)
            src_exists = bool(_query_rows(conn, f"MATCH (e:Entity) WHERE e.name = '{src}' RETURN e.name"))
            tgt_exists = bool(_query_rows(conn, f"MATCH (e:Entity) WHERE e.name = '{tgt}' RETURN e.name"))
            if src_exists and tgt_exists:
                conn.execute(
                    f"MATCH (a:Entity), (b:Entity) WHERE a.name = '{src}' AND b.name = '{tgt}' "
                    f"CREATE (a)-[:RELATES_TO {{relation: '{rtype}', memory_id: '{mid}'}}]->(b)"
                )
    except Exception as e:
        logger.error("Failed to add entities to graph: %s", e)


def search_entities(query: str, limit: int = 20) -> List[dict]:
    """Search entities by name substring match, returns entities with relations."""
    conn = _get_connection()
    if not conn:
        return []

    try:
        q = _escape(query)
        rows = _query_rows(conn, f"MATCH (e:Entity) WHERE e.name CONTAINS '{q}' RETURN e.name, e.type, e.memory_ids LIMIT {limit}")

        results = []
        for row in rows:
            name = row[0]
            ename = _escape(name)
            rel_rows = _query_rows(conn, f"MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) WHERE a.name = '{ename}' RETURN b.name, r.relation LIMIT 20")
            relations = [{"target": rr[0], "relation": rr[1]} for rr in rel_rows]
            results.append({
                "name": name,
                "type": row[1],
                "memory_ids": row[2],
                "relations": relations,
            })
        return results
    except Exception as e:
        logger.error("Graph search failed: %s", e)
        return []


def list_entities(limit: int = 100) -> List[dict]:
    """List all entities in the graph."""
    conn = _get_connection()
    if not conn:
        return []

    try:
        rows = _query_rows(conn, f"MATCH (e:Entity) RETURN e.name, e.type, e.memory_ids LIMIT {limit}")
        return [{"name": row[0], "type": row[1], "memory_count": len(row[2])} for row in rows]
    except Exception as e:
        logger.error("Graph list failed: %s", e)
        return []
