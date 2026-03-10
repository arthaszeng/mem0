#!/usr/bin/env python3
"""Migrate project_members.role from old 3-value enum to new 4-value enum.

Mapping:
  admin  -> owner   (existing admins become owners)
  normal -> read_write
  read   -> read_only

Usage (from repo root):
  python scripts/migrate_roles.py [--db /path/to/openmemory.db]

SQLite stores Enum values as plain strings so no ALTER TYPE is needed;
we just UPDATE the column values.
"""
import argparse
import os
import sqlite3
import sys

ROLE_MAP = {
    "admin": "owner",
    "normal": "read_write",
    "read": "read_only",
}


def migrate(db_path: str, dry_run: bool = False):
    if not os.path.exists(db_path):
        print(f"ERROR: database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, role FROM project_members")
    rows = cur.fetchall()
    print(f"Found {len(rows)} project_member rows")

    updated = 0
    for row_id, old_role in rows:
        new_role = ROLE_MAP.get(old_role)
        if new_role:
            if not dry_run:
                cur.execute(
                    "UPDATE project_members SET role = ? WHERE id = ?",
                    (new_role, row_id),
                )
            print(f"  {row_id}: {old_role} -> {new_role}")
            updated += 1
        else:
            print(f"  {row_id}: {old_role} (no change)")

    if not dry_run:
        conn.commit()
        print(f"\nCommitted {updated} updates.")
    else:
        print(f"\n[DRY RUN] Would update {updated} rows.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate project roles")
    default_db = "/data/openmemory.db" if os.path.isdir("/data") else "./openmemory.db"
    parser.add_argument("--db", default=default_db, help="Path to SQLite DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()
    migrate(args.db, dry_run=args.dry_run)
