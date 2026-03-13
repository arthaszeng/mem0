"""v1.1: add agent_id, run_id to memories

Revision ID: v1_1_entity_scoping
Revises: v0_8_lifecycle
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = "v1_1_entity_scoping"
down_revision = "v0_8_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(sa.Column("agent_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("run_id", sa.String(), nullable=True))
        batch_op.create_index("idx_memory_agent", ["agent_id"])
        batch_op.create_index("idx_memory_run", ["run_id"])


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.drop_index("idx_memory_run")
        batch_op.drop_index("idx_memory_agent")
        batch_op.drop_column("run_id")
        batch_op.drop_column("agent_id")
