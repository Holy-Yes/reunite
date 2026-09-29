from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Json = JSON().with_variant(JSONB(), "postgresql")

STAFF_ROLES = ("desk", "admin")                    # full desk/admin power
HANDOVER_ROLES = STAFF_ROLES + ("security_guard",)  # can also complete someone else's handover


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def _tz() -> DateTime:
    return DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(16), default="student")  # student | desk | admin | security_guard
    roll_no: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    venue: Mapped[str | None] = mapped_column(String(80), nullable=True)  # desk staff: the place they log for
    notify_push: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(_tz())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    centroid_lon: Mapped[float] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float)
    polygon: Mapped[dict | None] = mapped_column(Json, nullable=True)
    aliases: Mapped[list] = mapped_column(Json, default=list)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_pool", "kind", "status", "category_group", "occurred_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ticket_no: Mapped[str] = mapped_column(String(16), unique=True)
    kind: Mapped[str] = mapped_column(String(8))  # lost | found
    status: Mapped[str] = mapped_column(String(16), default="processing")
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    attributes: Mapped[dict] = mapped_column(Json, default=dict)
    hidden_attributes: Mapped[dict] = mapped_column(Json, default=dict)
    category: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    category_group: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    zone_id: Mapped[str] = mapped_column(String(64), ForeignKey("zones.id"))
    occurred_from: Mapped[datetime] = mapped_column(_tz())
    occurred_to: Mapped[datetime] = mapped_column(_tz())
    custody_zone_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("zones.id"), nullable=True)
    # Exact pin, when the person dropped one on the map. Private: only the owner, desk and admin ever see it.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_tier: Mapped[str] = mapped_column(String(8), default="low")
    redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    text_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    clip_text_embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    routed_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)  # unclaimed: handed on to a desk
    routed_to: Mapped[str | None] = mapped_column(String(120), nullable=True)

    images: Mapped[list[ItemImage]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemImage.created_at"
    )
    owner: Mapped[User] = relationship(foreign_keys=[owner_id])


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    public_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detections: Mapped[list] = mapped_column(Json, default=list)
    primary_crop: Mapped[dict | None] = mapped_column(Json, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)

    item: Mapped[Item] = relationship(back_populates="images")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("lost_item_id", "found_item_id", name="uq_match_pair"),
        Index("ix_matches_lost_score", "lost_item_id", "score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    lost_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id", ondelete="CASCADE"))
    found_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(16))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[list] = mapped_column(Json, default=list)  # the why breakdown
    model_version: Mapped[str] = mapped_column(String(64), default="hand-v1")
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)

    lost_item: Mapped[Item] = relationship(foreign_keys=[lost_item_id])
    found_item: Mapped[Item] = relationship(foreign_keys=[found_item_id])


_OPEN_CLAIM = "status in ('draft','pending_review','needs_more_info')"


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index(
            "uq_open_claim",
            "item_id",
            "claimant_id",
            unique=True,
            postgresql_where=text(_OPEN_CLAIM),
            sqlite_where=text(_OPEN_CLAIM),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    match_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("matches.id"), nullable=True)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id"), index=True)  # the found item
    claimant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    questions: Mapped[list] = mapped_column(Json, default=list)
    answers: Mapped[list] = mapped_column(Json, default=list)
    answer_scores: Mapped[dict] = mapped_column(Json, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signals: Mapped[dict] = mapped_column(Json, default=dict)
    verified_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    more_info_asked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow, onupdate=utcnow)

    item: Mapped[Item] = relationship(foreign_keys=[item_id])
    claimant: Mapped[User] = relationship(foreign_keys=[claimant_id])
    match: Mapped[Match | None] = relationship(foreign_keys=[match_id])


class Handover(Base):
    __tablename__ = "handovers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), unique=True)
    code_hash: Mapped[str] = mapped_column(String(160))
    token_jti: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(_tz())
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    id_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    tip_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # a pledge to settle in person; never processed here
    tip_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tip_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)


class Tag(Base):
    """A QR sticker for things people lose often (keys, luggage, a laptop bag). Anyone can scan it, no account needed."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class TagThread(Base):
    """One finder's conversation about a tag. Its id is the finder's only credential, kept in their browser."""

    __tablename__ = "tag_threads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tag_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class TagMessage(Base):
    __tablename__ = "tag_messages"
    __table_args__ = (Index("ix_tag_messages_thread_at", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    thread_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tag_threads.id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(String(8))  # finder | owner
    body: Mapped[str] = mapped_column(String(600))
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class Message(Base):
    """Relay chat between a claimant and a finder. Identities stay as roles; there is no contact info in the row."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_claim_at", "claim_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(600))
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class ItemEvent(Base):
    __tablename__ = "item_events"
    __table_args__ = (Index("ix_events_item_at", "item_id", "at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str] = mapped_column(String(16), default="system")
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class AttributeLabel(Base):
    __tablename__ = "attribute_labels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("items.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(32))
    old_value: Mapped[dict | list | str | None] = mapped_column(Json, nullable=True)
    new_value: Mapped[dict | list | str | None] = mapped_column(Json, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notif_user_read", "user_id", "read_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    href: Mapped[str] = mapped_column(String(300), default="/")
    data: Mapped[dict] = mapped_column(Json, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
    channels: Mapped[list] = mapped_column(Json, default=list)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(600), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_queue", "status", "run_after"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # ingest | extract | match | notify
    payload: Mapped[dict] = mapped_column(Json, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(_tz(), default=utcnow)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_tz(), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(_tz(), nullable=True)
