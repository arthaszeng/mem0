"""
Recovery script: rebuild SQLite metadata from Qdrant vector payloads.

Run inside the MCP container:
    python recover_from_qdrant.py

This reads all points from the Qdrant 'openmemory' collection and
creates corresponding User, App, and Memory rows in SQLite.
"""

import datetime
import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL", "")

from app.database import SessionLocal, engine, Base
from app.models import User, App, Memory, MemoryState, Category

from qdrant_client import QdrantClient


QDRANT_HOST = os.getenv("QDRANT_HOST", "mem0_store")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("QDRANT_COLLECTION", "openmemory")


def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime.datetime):
        return val
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    info = client.get_collection(COLLECTION)
    total = info.points_count
    print(f"Qdrant collection '{COLLECTION}': {total} points")

    all_points = []
    offset = None
    while True:
        result = client.scroll(
            collection_name=COLLECTION,
            limit=100,
            offset=offset,
            with_payload=True,
        )
        points, next_offset = result
        all_points.extend(points)
        print(f"  fetched {len(all_points)}/{total} ...")
        if next_offset is None:
            break
        offset = next_offset

    print(f"\nTotal points retrieved: {len(all_points)}")

    user_cache = {}
    app_cache = {}

    def get_or_create_user(user_id_str: str) -> User:
        if user_id_str in user_cache:
            return user_cache[user_id_str]
        user = db.query(User).filter(User.user_id == user_id_str).first()
        if not user:
            user = User(user_id=user_id_str, name=user_id_str)
            db.add(user)
            db.flush()
            print(f"  + Created user: {user_id_str}")
        user_cache[user_id_str] = user
        return user

    def get_or_create_app(owner: User, app_name: str) -> App:
        key = (str(owner.id), app_name)
        if key in app_cache:
            return app_cache[key]
        app = db.query(App).filter(App.owner_id == owner.id, App.name == app_name).first()
        if not app:
            app = App(owner_id=owner.id, name=app_name, is_active=True)
            db.add(app)
            db.flush()
            print(f"  + Created app: {app_name} (owner={owner.user_id})")
        app_cache[key] = app
        return app

    created = 0
    skipped = 0
    errors = 0

    for pt in all_points:
        try:
            payload = pt.payload or {}
            point_id = str(pt.id)

            user_id_str = payload.get("user_id", "arthaszeng")
            content = payload.get("data", "")
            if not content:
                skipped += 1
                continue

            app_name = payload.get("mcp_client") or payload.get("source_app") or "openmemory"
            created_at = parse_dt(payload.get("created_at"))
            updated_at = parse_dt(payload.get("updated_at"))

            mem_uuid = uuid.UUID(point_id)
            existing = db.query(Memory).filter(Memory.id == mem_uuid).first()
            if existing:
                skipped += 1
                continue

            user = get_or_create_user(user_id_str)
            app = get_or_create_app(user, app_name)

            metadata = {}
            for key in ("domain", "categories", "tags", "hash", "source_app", "mcp_client"):
                if key in payload:
                    metadata[key] = payload[key]

            memory = Memory(
                id=mem_uuid,
                user_id=user.id,
                app_id=app.id,
                content=content,
                metadata_=metadata,
                state=MemoryState.active,
                created_at=created_at or datetime.datetime.now(datetime.UTC),
                updated_at=updated_at or created_at or datetime.datetime.now(datetime.UTC),
            )
            db.add(memory)
            created += 1

        except Exception as e:
            errors += 1
            print(f"  ! Error processing point {pt.id}: {e}")

    db.commit()
    db.close()

    print(f"\n=== Recovery complete ===")
    print(f"  Created: {created}")
    print(f"  Skipped: {skipped} (already exist or empty)")
    print(f"  Errors:  {errors}")
    print(f"  Total points: {len(all_points)}")


if __name__ == "__main__":
    main()
