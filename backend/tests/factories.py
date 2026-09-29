from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.ml.attrs import attr
from app.models import Item, Match, User
from app import taxonomy
from app.services.items import next_ticket

T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def user(db, email: str, role: str = "student", roll_no: str | None = None) -> User:
    u = User(email=email, role=role, roll_no=roll_no)
    db.add(u)
    db.commit()
    return u


def item(db, owner: User, kind: str, category: str = "bottle", zone: str = "z_library", *, attrs: dict | None = None, status: str = "open", when: datetime | None = None, tier: str | None = None) -> Item:
    a = {"category": attr(category, 0.95, "text"), "colors": [attr("blue", 0.95, "text")], "marks": []}
    a.update(attrs or {})
    t = when or (T0 if kind == "lost" else T0 + timedelta(hours=6))
    it = Item(
        ticket_no=next_ticket(db, kind), kind=kind, status=status, owner_id=owner.id, description="test item", attributes=a,
        hidden_attributes={}, category=category, category_group=taxonomy.category_group(category), zone_id=zone,
        occurred_from=t, occurred_to=t + (timedelta(hours=4) if kind == "lost" else timedelta(0)),
        custody_zone_id="z_gate" if kind == "found" else None, value_tier=tier or ("high" if category in ("laptop", "phone") else "low"),
    )
    db.add(it)
    db.commit()
    return it


def match(db, lost: Item, found: Item, score: float = 0.8) -> Match:
    m = Match(lost_item_id=lost.id, found_item_id=found.id, score=score, band="strong", rank=1, features=[])
    db.add(m)
    db.commit()
    return m
