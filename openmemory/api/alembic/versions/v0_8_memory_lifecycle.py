"""v0.8: add expires_at, memory_type, expired state to memories

Revision ID: v0_8_lifecycle
Revises: afd00efbd06b
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = "v0_8_lifecycle"
down_revision = "afd00efbd06b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("memory_type", sa.String(), nullable=True))
        batch_op.create_index("idx_memory_expires", ["expires_at"])
        batch_op.create_index("idx_memory_type", ["memory_type"])


def downgrade() -> None:
    with op.batch_alter_table("memories") as batch_op:
        batch_op.drop_index("idx_memory_type")
        batch_op.drop_index("idx_memory_expires")
        batch_op.drop_column("memory_type")
        batch_op.drop_column("expires_at")
