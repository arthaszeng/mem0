"""v1.7: drop memory_type and agent_id from memories

These columns are redundant:
- memory_type is superseded by the domain/categories/tags classification system
- agent_id duplicates app_id (source app already tracked via the apps table)

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


def upgrade() -> None:
    conn = op.get_bind()
    indexes = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memories'")
    ).fetchall()
    index_names = {row[0] for row in indexes}

    with op.batch_alter_table("memories") as batch_op:
        if "idx_memory_agent" in index_names:
            batch_op.drop_index("idx_memory_agent")
        batch_op.drop_column("agent_id")
        batch_op.drop_column("memory_type")


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(sa.Column("memory_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("agent_id", sa.String(), nullable=True))
        batch_op.create_index("idx_memory_agent", ["agent_id"])
