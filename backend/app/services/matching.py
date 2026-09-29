"""Glue between the database and the matcher: build views, generate candidates, score, store, notify."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..ml.embed_util import from_bytes
from ..ml.matching import candidates, features as F, scorer
from ..models import Claim, Item, Match, User
from . import events
from .notify import notify
from .zones import zone_names

log = logging.getLogger("reunite.match")
POOL_STATUS = ("open", "matched")


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def view_from_item(item: Item) -> F.ItemView:
    attrs = item.attributes or {}
    cat = attrs.get("category") or {}
    return F.ItemView(
        id=str(item.id),
        kind=item.kind,
        zone_id=item.zone_id,
        occurred_from=aware(item.occurred_from),
        occurred_to=aware(item.occurred_to),
        category=cat.get("value"),
        category_conf=float(cat.get("confidence", 0.0)),
        category_dist=F.dist_from_attr(cat),
        colors=[c["value"] for c in attrs.get("colors", [])],
        brand=(attrs.get("brand") or {}).get("value"),
        marks=[m["value"] for m in attrs.get("marks", [])],
        image_embs=[e for e in (from_bytes(i.embedding) for i in item.images) if e is not None],
        text_emb=from_bytes(item.text_embedding),
        clip_text_emb=from_bytes(item.clip_text_embedding),
    )


def _pool(db: Session, item: Item) -> list[Item]:
    opposite = "found" if item.kind == "lost" else "lost"
    q = select(Item).where(Item.kind == opposite, Item.status.in_(POOL_STATUS), Item.id != item.id)
    return list(db.scalars(q))


def run_match(db: Session, item_id: uuid.UUID) -> list[Match]:
    """Score `item` against the opposite pool and store the matches. Returns the stored matches."""
    s = get_settings()
    item = db.get(Item, item_id)
    if item is None or item.status in ("returned", "closed"):
        return []
    names = zone_names(db)
    me = view_from_item(item)
    pool_items = {str(i.id): i for i in _pool(db, item)}
    pool_views = [view_from_item(i) for i in pool_items.values()]
    chosen = candidates.top_candidates(me, pool_views, s.candidate_pool)

    kept: dict[tuple[uuid.UUID, uuid.UUID], Match] = {}
    for cand in chosen:
        lost_v, found_v = (me, cand) if item.kind == "lost" else (cand, me)
        feats = F.compute_features(lost_v, found_v, names)
        if feats is None:
            continue
        res = scorer.score_pair(feats)
        if res.score < s.min_show:
            continue
        lost_id, found_id = uuid.UUID(lost_v.id), uuid.UUID(found_v.id)
        m = db.scalar(select(Match).where(Match.lost_item_id == lost_id, Match.found_item_id == found_id))
        if m is None:
            m = Match(lost_item_id=lost_id, found_item_id=found_id, score=res.score, band=res.band, features=res.contributions, model_version=res.model_version)
            db.add(m)
        else:
            m.score, m.band, m.features, m.model_version = res.score, res.band, res.contributions, res.model_version
        kept[(lost_id, found_id)] = m
    db.flush()

    # Matches this item had before that no longer qualify go away, unless a claim or feedback depends on them.
    col = Match.lost_item_id if item.kind == "lost" else Match.found_item_id
    for old in db.scalars(select(Match).where(col == item.id)):
        key = (old.lost_item_id, old.found_item_id)
        if key in kept or old.feedback or db.scalar(select(Claim.id).where(Claim.match_id == old.id).limit(1)):
            continue
        db.delete(old)
    db.flush()

    affected = {m.lost_item_id for m in kept.values()} | ({item.id} if item.kind == "lost" else set())
    for lost_id in affected:
        _rerank(db, lost_id)
    if item.status == "processing":  # extraction is done by the time we match
        item.status = "open"
    _update_status(db, item, list(kept.values()))
    for m in kept.values():
        other = db.get(Item, m.found_item_id if item.kind == "lost" else m.lost_item_id)
        if other is not None:
            _update_status(db, other, None)
    db.commit()
    return list(kept.values())


def _rerank(db: Session, lost_id: uuid.UUID) -> None:
    rows = list(db.scalars(select(Match).where(Match.lost_item_id == lost_id).order_by(Match.score.desc())))
    for i, m in enumerate(rows, start=1):
        m.rank = i


def _update_status(db: Session, item: Item, _matches: list[Match] | None) -> None:
    """open <-> matched, based on whether any stored match reaches the Possible band. Claimed and later states are left alone."""
    if item.status not in POOL_STATUS:
        return
    col = Match.lost_item_id if item.kind == "lost" else Match.found_item_id
    best = db.scalar(select(Match.score).where(col == item.id).order_by(Match.score.desc()).limit(1))
    matched = best is not None and best >= get_settings().band_possible
    item.status = "matched" if matched else "open"
    if matched and not events.has_event(db, item.id, "matched"):
        events.add_event(db, item.id, "matched", actor_role="system", payload={"score": round(best, 3)})


def notify_matches(db: Session, item_id: uuid.UUID) -> int:
    """Tell the owner of each lost item about matches at or above NOTIFY_THRESHOLD, once per match."""
    s = get_settings()
    item = db.get(Item, item_id)
    if item is None:
        return 0
    col = Match.lost_item_id if item.kind == "lost" else Match.found_item_id
    rows = db.scalars(select(Match).where(col == item.id, Match.score >= s.notify_threshold, Match.notified_at.is_(None)))
    n = 0
    for m in rows:
        lost = db.get(Item, m.lost_item_id)
        if lost is None or lost.status in ("returned", "closed") or m.feedback == "not_mine":
            continue
        cat = ((lost.attributes or {}).get("category") or {}).get("value", "item").replace("_", " ")
        notify(
            db, lost.owner_id, "new_match",
            title=f"A possible match for your {cat}",
            body=f"{m.band.replace('_', ' ').capitalize()} match, {round(m.score * 100)}%. See why it fits.",
            href=f"/matches?item={lost.id}",
            data={"match_id": str(m.id), "lost_item_id": str(lost.id)},
        )
        m.notified_at = datetime.now(timezone.utc)
        n += 1
    db.commit()
    return n
