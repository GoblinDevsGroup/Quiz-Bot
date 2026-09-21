"""track moderation notifications and who moderated a quiz

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quizzes", sa.Column("moderated_by_name", sa.String(255), nullable=True))
    op.create_table(
        "moderation_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("quiz_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_moderation_notifications_quiz_id", "moderation_notifications", ["quiz_id"])


def downgrade() -> None:
    op.drop_index("ix_moderation_notifications_quiz_id", table_name="moderation_notifications")
    op.drop_table("moderation_notifications")
    op.drop_column("quizzes", "moderated_by_name")
