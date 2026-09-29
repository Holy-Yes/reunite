"""relay chat, desk venue, unclaimed routing, tip pledge

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(length=600), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_claim_at", "messages", ["claim_id", "created_at"])
    op.add_column("users", sa.Column("venue", sa.String(length=80), nullable=True))
    op.add_column("items", sa.Column("routed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("items", sa.Column("routed_to", sa.String(length=120), nullable=True))
    op.add_column("handovers", sa.Column("tip_amount", sa.Integer(), nullable=True))
    op.add_column("handovers", sa.Column("tip_note", sa.String(length=300), nullable=True))
    op.add_column("handovers", sa.Column("tip_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for t, c in (("handovers", "tip_at"), ("handovers", "tip_note"), ("handovers", "tip_amount"), ("items", "routed_to"), ("items", "routed_at"), ("users", "venue")):
        op.drop_column(t, c)
    op.drop_index("ix_messages_claim_at", table_name="messages")
    op.drop_table("messages")
