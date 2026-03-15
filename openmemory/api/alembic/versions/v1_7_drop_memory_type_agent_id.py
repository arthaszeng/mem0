"""v1.7: drop memory_type/agent_id columns and agent_instructions table

- memory_type is superseded by the domain/categories/tags classification system
- agent_id duplicates app_id (source app already tracked via the apps table)
- agent_instructions table is no longer needed without per-agent scoping

Revision ID: v1_7_drop_memory_type_agent_id
Revises: v1_2_agent_instructions
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa

revision = "v1_7_drop_memory_type_agent_id"
down_revision = "v1_2_agent_instructions"
branch_labels = None
depends_on = None


def _get_index_names(table_name: str):
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'")
    ).fetchall()
    return {row[0] for row in rows}


def _get_column_names(table_name: str):
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def upgrade() -> None:
    mem_columns = _get_column_names("memories")
    mem_indexes = _get_index_names("memories")

    cols_to_drop = [c for c in ("agent_id", "memory_type") if c in mem_columns]
    if cols_to_drop or "idx_memory_agent" in mem_indexes:
        with op.batch_alter_table("memories") as batch_op:
            if "idx_memory_agent" in mem_indexes:
                batch_op.drop_index("idx_memory_agent")
            for col in cols_to_drop:
                batch_op.drop_column(col)

    conn = op.get_bind()
    tables = {row[0] for row in conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()}
    if "agent_instructions" in tables:
        ai_indexes = _get_index_names("agent_instructions")
        for idx in ("idx_agent_instr_lookup", "ix_agent_instructions_agent_id",
                     "ix_agent_instructions_project_id", "ix_agent_instructions_user_id"):
            if idx in ai_indexes:
                op.drop_index(idx, "agent_instructions")
        op.drop_table("agent_instructions")


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(sa.Column("memory_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("agent_id", sa.String(), nullable=True))
        batch_op.create_index("idx_memory_agent", ["agent_id"])

    op.create_table(
        "agent_instructions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("instructions", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_instructions_user_id", "agent_instructions", ["user_id"])
    op.create_index("ix_agent_instructions_project_id", "agent_instructions", ["project_id"])
    op.create_index("ix_agent_instructions_agent_id", "agent_instructions", ["agent_id"])
    op.create_index("idx_agent_instr_lookup", "agent_instructions", ["user_id", "project_id", "agent_id"], unique=True)
