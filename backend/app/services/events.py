from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ItemEvent

PUBLIC_TYPES = ("reported", "matched", "claimed", "verified", "handed_over", "routed", "closed")


def add_event(db: Session, item_id: uuid.UUID, type_: str, actor_id: uuid.UUID | None = None, actor_role: str = "system", payload: dict | None = None) -> ItemEvent:
    if type_ not in PUBLIC_TYPES:
        raise ValueError(f"unknown event type {type_}")
    ev = ItemEvent(item_id=item_id, type=type_, actor_id=actor_id, actor_role=actor_role, payload=payload or {})
    db.add(ev)
    return ev


def has_event(db: Session, item_id: uuid.UUID, type_: str) -> bool:
    return db.scalar(select(ItemEvent.id).where(ItemEvent.item_id == item_id, ItemEvent.type == type_).limit(1)) is not None


def timeline(db: Session, item_id: uuid.UUID) -> list[dict]:
    rows = db.scalars(select(ItemEvent).where(ItemEvent.item_id == item_id, ItemEvent.type.in_(PUBLIC_TYPES)).order_by(ItemEvent.at))
    return [
        {"id": str(e.id), "item_id": str(e.item_id), "type": e.type, "actor_role": _role(e.actor_role), "at": iso(e.at), **({"note": e.payload["note"]} if e.payload.get("note") else {})}
        for e in rows
    ]


def _role(r: str) -> str:
    return {"student": "student", "finder": "finder", "desk": "desk", "admin": "desk", "system": "system"}.get(r, "system")


def iso(dt) -> str:  # noqa: ANN001
    from datetime import timezone

    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
