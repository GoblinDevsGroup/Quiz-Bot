"""add quiz timer and shuffle options

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quizzes", sa.Column("time_limit_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "quizzes", sa.Column("shuffle_questions", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "quizzes", sa.Column("shuffle_options", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("quizzes", "shuffle_options")
    op.drop_column("quizzes", "shuffle_questions")
    op.drop_column("quizzes", "time_limit_seconds")
