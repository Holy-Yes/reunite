"""qr tags with anonymous finder threads

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tags_code", "tags", ["code"], unique=True)
    op.create_index("ix_tags_owner_id", "tags", ["owner_id"])
    op.create_table(
        "tag_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_threads_tag_id", "tag_threads", ["tag_id"])
    op.create_table(
        "tag_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("sender", sa.String(length=8), nullable=False),
        sa.Column("body", sa.String(length=600), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["tag_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_messages_thread_at", "tag_messages", ["thread_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_tag_messages_thread_at", table_name="tag_messages")
    op.drop_table("tag_messages")
    op.drop_index("ix_tag_threads_tag_id", table_name="tag_threads")
    op.drop_table("tag_threads")
    op.drop_index("ix_tags_owner_id", table_name="tags")
    op.drop_index("ix_tags_code", table_name="tags")
    op.drop_table("tags")
