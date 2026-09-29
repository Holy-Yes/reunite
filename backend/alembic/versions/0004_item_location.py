"""exact pin for where an item was lost or found

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 22:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("items", sa.Column("lon", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "lon")
    op.drop_column("items", "lat")
