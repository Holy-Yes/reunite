"""Admin insights and the ops scene. Everything is aggregated to zones and items, never people:
finders appear as "Finder A", "Finder B", and the ops scene carries no user ids or exact positions."""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, Handover, Item, Match, User, Zone
from .events import iso

RANGES = {"7d": 7, "30d": 30, "term": 120}


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def since(range_: str) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=RANGES.get(range_, 7))


def _lost(db: Session, start: datetime) -> list[Item]:
    return [i for i in db.scalars(select(Item).where(Item.kind == "lost")) if aware(i.created_at) >= start]


def summary(db: Session, range_: str) -> dict:
    start = since(range_)
    lost = _lost(db, start)
    returned = [i for i in lost if i.status == "returned"]
    rate = len(returned) / len(lost) if lost else 0.0

    hours: list[float] = []
    for h, c in db.execute(select(Handover, Claim).join(Claim, Claim.id == Handover.claim_id).where(Handover.confirmed_at.is_not(None))):
        if aware(h.confirmed_at) < start or c.match is None:
            continue
        hours.append((aware(h.confirmed_at) - aware(c.match.lost_item.created_at)).total_seconds() / 3600)
    median = round(statistics.median(hours), 1) if hours else None

    fb = Counter(m.feedback for m in db.scalars(select(Match).where(Match.feedback.in_(("mine", "not_mine")))) if m.feedback_at and aware(m.feedback_at) >= start)
    precision = fb["mine"] / (fb["mine"] + fb["not_mine"]) if (fb["mine"] + fb["not_mine"]) else None

    all_lost = list(db.scalars(select(Item).where(Item.kind == "lost")))
    open_lost = sum(1 for i in all_lost if i.status in ("open", "matched", "claimed"))
    open_found = sum(1 for i in db.scalars(select(Item).where(Item.kind == "found")) if i.status in ("open", "matched", "claimed"))

    # 7-day trend: recovery rate over the seven days ending each day
    trend = []
    now = datetime.now(timezone.utc)
    for d in range(6, -1, -1):
        end = now - timedelta(days=d)
        window = [i for i in all_lost if end - timedelta(days=7) <= aware(i.created_at) <= end]
        done = [i for i in window if i.status == "returned" and aware(i.updated_at) <= end]
        trend.append({"date": end.date().isoformat(), "recovery_rate": round(len(done) / len(window), 3) if window else 0.0})
    return {
        "recovery_rate": round(rate, 3),
        "median_hours_to_reunite": median,
        "live_precision": round(precision, 3) if precision is not None else None,
        "open_lost": open_lost,
        "open_found": open_found,
        "trend": trend,
    }


def hotspots(db: Session, range_: str) -> list[dict]:
    start = since(range_)
    lost, found = Counter(), Counter()
    for i in db.scalars(select(Item)):
        if aware(i.created_at) < start:
            continue
        (lost if i.kind == "lost" else found)[i.zone_id] += 1
    zones = [z.id for z in db.scalars(select(Zone))]
    return sorted(({"zone_id": z, "lost": lost[z], "found": found[z]} for z in zones), key=lambda r: -r["lost"])


def heatmap(db: Session, range_: str) -> list[list[int]]:
    """7 (Monday first) by 24 counts of the midpoint of each lost window."""
    grid = [[0] * 24 for _ in range(7)]
    for i in _lost(db, since(range_)):
        mid = aware(i.occurred_from) + (aware(i.occurred_to) - aware(i.occurred_from)) / 2
        grid[mid.weekday()][mid.hour] += 1
    return grid


def categories(db: Session, range_: str) -> list[dict]:
    c = Counter(i.category or "unknown" for i in _lost(db, since(range_)))
    return [{"category": k, "count": v} for k, v in c.most_common()]


def finders(db: Session, range_: str) -> list[dict]:
    start = since(range_)
    returned = Counter()
    for i in db.scalars(select(Item).where(Item.kind == "found", Item.status == "returned")):
        if aware(i.updated_at) >= start:
            returned[i.owner_id] += 1
    users = {u.id: u for u in db.scalars(select(User).where(User.points > 0))}
    ranked = sorted(users.values(), key=lambda u: (-u.points, str(u.id)))[:10]
    return [{"label": f"Finder {chr(65 + i)}", "points": u.points, "returned": returned.get(u.id, 0)} for i, u in enumerate(ranked)]


def ops_scene(db: Session, start: datetime | None, end: datetime | None) -> dict:
    """Zone-level pins, arcs and heat with timestamps, so the map can replay a week. No user ids."""
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=7)
    pins, heat = [], Counter()
    for i in db.scalars(select(Item)):
        t0 = aware(i.occurred_from)
        if t0 < start - timedelta(days=30) or t0 > end:
            continue
        t1 = aware(i.closed_at or i.updated_at) if i.status in ("returned", "closed") else end
        pins.append({"id": i.ticket_no, "zone_id": i.zone_id, "kind": i.kind, "category": i.category, "from": iso(t0), "to": iso(t1), "status": i.status})
        if i.kind == "lost" and t0 >= start:
            heat[i.zone_id] += 1
    arcs = []
    for m in db.scalars(select(Match).where(Match.score >= 0.2)):
        created = aware(m.created_at)
        if created > end:
            continue
        arcs.append(
            {
                "lost_zone_id": m.lost_item.zone_id,
                "found_zone_id": m.found_item.zone_id,
                "band": m.band,
                "score": round(m.score, 3),
                "from": iso(created),
                "to": iso(aware(m.found_item.closed_at or m.found_item.updated_at) if m.found_item.status in ("returned", "closed") else end),
            }
        )
    return {"pins": pins, "arcs": arcs, "heat": [{"zone_id": z, "lost": n} for z, n in heat.most_common()], "from": iso(start), "to": iso(end)}
