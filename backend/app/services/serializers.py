"""Model to JSON. The shapes match the types in WEBSITE_PROMPT.md section 6.
`public_item` is built from a whitelist, so hidden details cannot appear in it by construction."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..ml import pipeline
from ..models import Claim, Handover, Item, Match, User
from . import claims as claims_svc
from .events import iso


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "role": u.role, "roll_no": u.roll_no, "notify_push": u.notify_push, "notify_email": u.notify_email, "points": u.points, "venue": u.venue}


def item_out(db: Session, item: Item) -> dict:
    """The owner (and desk and admin) view, hidden attributes included."""
    col = Match.lost_item_id if item.kind == "lost" else Match.found_item_id
    count = db.scalar(select(func.count(Match.id)).where(col == item.id, Match.score >= get_settings().min_show)) or 0
    return {
        "id": str(item.id),
        "ticket_no": item.ticket_no,
        "kind": item.kind,
        "status": item.status,
        "owner_id": str(item.owner_id),
        "description": item.description,
        "attributes": item.attributes or {},
        "photos": [{"id": str(i.id), "url": f"/media/original/{i.id}", "detections": i.detections or []} for i in item.images],
        "zone_id": item.zone_id,
        "occurred_from": iso(item.occurred_from),
        "occurred_to": iso(item.occurred_to),
        "custody_zone_id": item.custody_zone_id,
        "lat": item.lat,
        "lon": item.lon,
        "redacted": item.redacted,
        "routed_to": item.routed_to,
        "match_count": count,
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
    }


def public_item(item: Item) -> dict:
    """PublicItem: category, colors, brand, zone, date and a blurred photo. Nothing else, ever."""
    attrs = pipeline.public_attributes(item.attributes or {})
    out: dict = {
        "id": str(item.id),
        "ticket_no": item.ticket_no,
        "category": item.category,
        "colors": [c["value"] for c in attrs.get("colors", [])] if not item.redacted else [],
        "zone_id": item.zone_id,
        "found_at": iso(item.occurred_from),
    }
    brand = attrs.get("brand")
    if brand and not item.redacted:
        out["brand"] = brand["value"]
    if item.images and item.images[0].public_path:
        out["photo"] = {"url": f"/media/public/{item.images[0].id}.jpg", "blurred": True}
    if item.redacted:
        out["redacted"] = True
    return out


def match_out(m: Match) -> dict:
    return {
        "id": str(m.id),
        "lost_item_id": str(m.lost_item_id),
        "candidate": public_item(m.found_item),
        "score": round(m.score, 4),
        "band": m.band,
        "rank": m.rank,
        "why": m.features,
        "feedback": m.feedback,
        "created_at": iso(m.created_at),
    }


def claim_out(claim: Claim, staff: bool = False) -> dict:
    out = {
        "id": str(claim.id),
        "match_id": str(claim.match_id) if claim.match_id else None,
        "item_id": str(claim.item_id),
        "claimant_id": str(claim.claimant_id),
        "status": claim.status,
        "questions": claims_svc.public_questions(claim),
        "verified_by": claim.verified_by,
        "note": claim.decision_note,
        "item": public_item(claim.item),
        "must_be_reviewed_by_person": (claim.item.category or "") in get_settings().review_categories,
        "created_at": iso(claim.created_at),
    }
    if staff:
        out["review"] = {
            "score": claim.score,
            "answers": claims_svc.review_rows(claim),
            "signals": claim.signals,
            "claimant_email": claim.claimant.email,
            "private_details": claim.item.hidden_attributes or {},
        }
        out["category"] = claim.item.category
        out["ticket_no"] = claim.item.ticket_no
        out["age_hours"] = round((datetime.now(timezone.utc) - claims_svc.aware(claim.created_at)).total_seconds() / 3600, 1)
    return out
