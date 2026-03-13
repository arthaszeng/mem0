"""v1.2: add agent_instructions table

Revision ID: v1_2_agent_instructions
Revises: v1_1_entity_scoping
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa

revision = "v1_2_agent_instructions"
down_revision = "v1_1_entity_scoping"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index("idx_agent_instr_lookup", "agent_instructions")
    op.drop_index("ix_agent_instructions_agent_id", "agent_instructions")
    op.drop_index("ix_agent_instructions_project_id", "agent_instructions")
    op.drop_index("ix_agent_instructions_user_id", "agent_instructions")
    op.drop_table("agent_instructions")
