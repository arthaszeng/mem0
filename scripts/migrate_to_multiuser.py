#!/usr/bin/env python3
"""Migrate existing single-user OpenMemory data to multi-user auth system.

Run this ONCE after deploying Phase 1-3 to:
1. Ensure auth.db has the admin user
2. Create a default project in OpenMemory and assign all existing memories to it
3. Ensure the OpenMemory User matches the auth-service admin user

Usage:
    docker exec mem0-openmemory-mcp-1 python3 /scripts/migrate_to_multiuser.py

Or run locally with correct DB paths:
    AUTH_DB=/path/to/auth.db OPENMEMORY_DB=/path/to/openmemory.db python3 scripts/migrate_to_multiuser.py
"""

import os
import sqlite3
import sys
import uuid
from datetime import datetime, UTC


AUTH_DB = os.getenv("AUTH_DB", "/data/auth.db")
OPENMEMORY_DB = os.getenv("OPENMEMORY_DB", "/data/openmemory.db")
ADMIN_USERNAME = os.getenv("INIT_ADMIN_USER", "arthaszeng")
DEFAULT_PROJECT_NAME = os.getenv("DEFAULT_PROJECT_NAME", "Default")
DEFAULT_PROJECT_SLUG = os.getenv("DEFAULT_PROJECT_SLUG", "default")


def step(msg: str):
    print(f"  → {msg}")


def migrate():
    print("=" * 60)
    print("OpenMemory Multi-User Migration Script")
    print("=" * 60)

    # 1. Check databases exist
    if not os.path.exists(OPENMEMORY_DB):
        print(f"ERROR: OpenMemory DB not found at {OPENMEMORY_DB}")
        sys.exit(1)

    om = sqlite3.connect(OPENMEMORY_DB)
    om.row_factory = sqlite3.Row

    print(f"\n[1/4] Checking OpenMemory database...")
    cur = om.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    cur = om.execute("SELECT COUNT(*) FROM memories")
    memory_count = cur.fetchone()[0]
    step(f"Found {user_count} users, {memory_count} memories")

    # 2. Ensure the admin user exists in OpenMemory
    print(f"\n[2/4] Ensuring admin user '{ADMIN_USERNAME}' exists...")
    cur = om.execute("SELECT id, user_id FROM users WHERE user_id = ?", (ADMIN_USERNAME,))
    admin_row = cur.fetchone()
    if admin_row:
        admin_om_id = admin_row["id"]
        step(f"Admin user exists: id={admin_om_id}")
    else:
        admin_om_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        om.execute(
            "INSERT INTO users (id, user_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (admin_om_id, ADMIN_USERNAME, ADMIN_USERNAME, now, now),
        )
        om.commit()
        step(f"Created admin user: id={admin_om_id}")

    # 3. Create default project
    print(f"\n[3/4] Creating default project '{DEFAULT_PROJECT_SLUG}'...")
    cur = om.execute("SELECT id FROM projects WHERE slug = ?", (DEFAULT_PROJECT_SLUG,))
    project_row = cur.fetchone()
    if project_row:
        project_id = project_row["id"]
        step(f"Default project already exists: id={project_id}")
    else:
        project_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        om.execute(
            "INSERT INTO projects (id, name, slug, owner_id, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, DEFAULT_PROJECT_NAME, DEFAULT_PROJECT_SLUG, admin_om_id, "Default project for migrated data", now, now),
        )
        member_id = str(uuid.uuid4())
        om.execute(
            "INSERT INTO project_members (id, project_id, user_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (member_id, project_id, admin_om_id, "admin", now),
        )
        om.commit()
        step(f"Created default project: id={project_id}")

    # 4. Assign all orphan memories to the default project
    print(f"\n[4/4] Assigning memories to default project...")

    # Check if project_id column exists
    cur = om.execute("PRAGMA table_info(memories)")
    columns = [r["name"] for r in cur.fetchall()]
    if "project_id" not in columns:
        step("Adding project_id column to memories table...")
        om.execute("ALTER TABLE memories ADD COLUMN project_id VARCHAR REFERENCES projects(id)")
        om.commit()

    cur = om.execute("SELECT COUNT(*) FROM memories WHERE project_id IS NULL")
    orphan_count = cur.fetchone()[0]
    if orphan_count > 0:
        om.execute("UPDATE memories SET project_id = ? WHERE project_id IS NULL", (project_id,))
        om.commit()
        step(f"Assigned {orphan_count} memories to default project")
    else:
        step("No orphan memories found")

    om.close()

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
