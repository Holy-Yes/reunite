"""Unclaimed found items don't expire into a black hole: after a set number of days they go to a desk."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Claim, Item, Zone
from . import events
from .notify import notify

LIVE_CLAIM = ("draft", "pending_review", "needs_more_info", "approved", "auto_approved")


def route_unclaimed(db: Session, now: datetime | None = None) -> int:
    s = get_settings()
    if s.unclaimed_route_days <= 0:
        return 0
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=s.unclaimed_route_days)
    zone = db.get(Zone, s.unclaimed_route_zone) if s.unclaimed_route_zone else None
    n = 0
    stmt = select(Item).where(Item.kind == "found", Item.status.in_(("open", "matched")), Item.routed_at.is_(None), Item.created_at < cutoff)
    for it in db.scalars(stmt):
        if db.scalar(select(Claim.id).where(Claim.item_id == it.id, Claim.status.in_(LIVE_CLAIM)).limit(1)):
            continue
        it.routed_at, it.routed_to = now, s.unclaimed_route_label
        if zone is not None:
            it.custody_zone_id = zone.id
        events.add_event(db, it.id, "routed", None, "system", {"note": f"Nobody claimed it in {s.unclaimed_route_days} days, so it went to {s.unclaimed_route_label}."})
        notify(db, it.owner_id, "item_routed", "Your found item went to the desk", f"Nobody claimed it in {s.unclaimed_route_days} days. It is now with {s.unclaimed_route_label}.", f"/items/{it.id}", {"item_id": str(it.id)})
        n += 1
    db.commit()
    return n
