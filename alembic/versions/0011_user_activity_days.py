"""track which days each user was active

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_activity_days",
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("day", sa.Date(), primary_key=True),
    )
    op.create_index("ix_user_activity_days_day", "user_activity_days", ["day"])

    # Backfill from what history exists (sign-ups, quiz attempts, created
    # quizzes) so the stats aren't empty on day one. Days are in Tashkent time
    # to match what the bot records from now on.
    op.execute(
        """
        INSERT INTO user_activity_days (user_id, day)
        SELECT user_id, day FROM (
            SELECT id AS user_id, (created_at AT TIME ZONE 'Asia/Tashkent')::date AS day FROM users
            UNION
            SELECT user_id, (started_at AT TIME ZONE 'Asia/Tashkent')::date FROM quiz_attempts
            UNION
            SELECT creator_id, (created_at AT TIME ZONE 'Asia/Tashkent')::date FROM quizzes
        ) AS history
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_activity_days_day", table_name="user_activity_days")
    op.drop_table("user_activity_days")
