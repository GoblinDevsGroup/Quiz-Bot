"""add grade and moderation_number to quizzes

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quizzes", sa.Column("grade", sa.Integer(), nullable=True))
    op.add_column("quizzes", sa.Column("moderation_number", sa.Integer(), nullable=True))
    op.create_index("ix_quizzes_grade", "quizzes", ["grade"])
    op.create_index("ix_quizzes_moderation_number", "quizzes", ["moderation_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quizzes_moderation_number", table_name="quizzes")
    op.drop_index("ix_quizzes_grade", table_name="quizzes")
    op.drop_column("quizzes", "moderation_number")
    op.drop_column("quizzes", "grade")
