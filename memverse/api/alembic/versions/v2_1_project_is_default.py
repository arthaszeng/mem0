"""v2.1: add is_default column to projects table

v2.1.0 switches data filtering from user_id to project_id.
Each user must have exactly one default project; this column
tracks which one it is, preventing accidental deletion.

Revision ID: v2_1_project_is_default
Revises: v1_7_drop_memory_type_agent_id
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa

revision = "v2_1_project_is_default"
down_revision = "v1_7_drop_memory_type_agent_id"
branch_labels = None
depends_on = None


def _get_column_names(table_name: str):
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    cols = _get_column_names("projects")
    if "is_default" not in cols:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(
                sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=True)
            )
            batch_op.create_index("ix_projects_is_default", ["is_default"])

    # Mark each user's first-created project as their default
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE projects
        SET is_default = 1
        WHERE id IN (
            SELECT id FROM (
                SELECT id, owner_id,
                       ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY created_at ASC) AS rn
                FROM projects
            ) ranked
            WHERE rn = 1
        )
    """))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_is_default")
        batch_op.drop_column("is_default")
