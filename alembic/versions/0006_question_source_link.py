"""add question source_link

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("source_link", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "source_link")
