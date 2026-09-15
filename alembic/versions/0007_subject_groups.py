"""add subject_groups table

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subject_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("invite_link", sa.String(512), nullable=False),
        sa.Column("added_by_telegram_id", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_subject_groups_category_id", "subject_groups", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_subject_groups_category_id", table_name="subject_groups")
    op.drop_table("subject_groups")
