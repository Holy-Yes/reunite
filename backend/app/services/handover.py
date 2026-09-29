"""Handover: a signed token (the QR payload) plus a six-digit code, valid for 15 minutes.

The code is derived from the claim and a per-issue id with the server secret, so the claimant's app can
show it again after a reload while only a salted hash is stored for checking. Attempts are limited.
"""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..errors import ApiError
from ..models import HANDOVER_ROLES, Claim, Handover, Item, Match, User
from ..security import TokenError, make_handover_token, read_handover_token, salted_hash, verify_salted
from . import events
from .notify import notify

# Wrong-code attempts per confirming user (code entry does not say which handover it means).
_attempts: dict[str, list[float]] = {}


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _derive_code(claim_id: uuid.UUID, jti: str) -> str:
    key = get_settings().jwt_secret.encode()
    n = int.from_bytes(hmac.new(key, f"handover|{claim_id}|{jti}".encode(), hashlib.sha256).digest()[:8], "big")
    return f"{n % 1_000_000:06d}"


def issue(db: Session, claim: Claim) -> Handover:
    """Create the handover, or replace an expired or unused one (a new code each time)."""
    s = get_settings()
    jti = uuid.uuid4().hex
    expires = datetime.now(timezone.utc) + timedelta(minutes=s.handover_ttl_minutes)
    code = _derive_code(claim.id, jti)
    h = db.scalar(select(Handover).where(Handover.claim_id == claim.id))
    if h is None:
        h = Handover(claim_id=claim.id, code_hash=salted_hash(code), token_jti=jti, expires_at=expires)
        db.add(h)
    else:
        if h.confirmed_at:
            raise ApiError(409, "already_returned", "This item has already been handed over.")
        h.code_hash, h.token_jti, h.expires_at, h.attempts = salted_hash(code), jti, expires, 0
    db.flush()
    return h


def payload(claim: Claim, h: Handover) -> dict:
    """The Handover shape the client renders (QR payload and the big code)."""
    from .events import iso

    return {
        "claim_id": str(claim.id),
        "qr_payload": make_handover_token(claim.id, h.token_jti, aware(h.expires_at)),
        "code": _derive_code(claim.id, h.token_jti),
        "expires_at": iso(h.expires_at),
        "expired": aware(h.expires_at) < datetime.now(timezone.utc),
        "collect_zone_id": claim.item.custody_zone_id or claim.item.zone_id,
    }


def _limit(actor: User) -> None:
    now = time.time()
    window = get_settings().handover_ttl_minutes * 60
    hits = [t for t in _attempts.get(str(actor.id), []) if now - t < window]
    _attempts[str(actor.id)] = hits
    if len(hits) >= get_settings().handover_max_attempts:
        raise ApiError(429, "too_many_attempts", "Too many wrong codes. Wait a few minutes and try again.", retry_after=int(window - (now - hits[0])))


def _fail(actor: User, code: str, message: str, status: int = 400) -> ApiError:
    _attempts.setdefault(str(actor.id), []).append(time.time())
    left = max(get_settings().handover_max_attempts - len(_attempts[str(actor.id)]), 0)
    return ApiError(status, code, message, {"attempts_left": str(left)})


def reset_attempts() -> None:
    _attempts.clear()


def confirm(db: Session, actor: User, code: str | None, token: str | None, id_checked: bool) -> tuple[Claim, Item]:
    if not code and not token:
        raise ApiError(422, "invalid_request", "Enter the six-digit code or scan the QR.", {"code": "required"})
    _limit(actor)
    h: Handover | None = None
    if token:
        try:
            data = read_handover_token(token)
        except TokenError as e:
            if str(e) == "expired":
                raise ApiError(410, "handover_expired", "This code has expired. Ask the owner for a new one.") from e
            raise _fail(actor, "invalid_code", "That QR isn't valid.") from e
        h = db.scalar(select(Handover).where(Handover.claim_id == uuid.UUID(data["claim"])))
        if h is None or h.token_jti != data["jti"]:
            raise _fail(actor, "invalid_code", "That QR has been replaced by a newer one.")
    else:
        now = datetime.now(timezone.utc)
        active = db.scalars(select(Handover).where(Handover.confirmed_at.is_(None)))
        for cand in active:
            if hmac.compare_digest(_derive_code(cand.claim_id, cand.token_jti), code or "") and verify_salted(code or "", cand.code_hash):
                if aware(cand.expires_at) < now:
                    raise ApiError(410, "handover_expired", "This code has expired. Ask the owner for a new one.")
                h = cand
                break
        if h is None:
            raise _fail(actor, "invalid_code", "That code doesn't match.")

    if h.confirmed_at:
        raise ApiError(409, "already_returned", "This item has already been handed over.")
    if aware(h.expires_at) < datetime.now(timezone.utc):
        raise ApiError(410, "handover_expired", "This code has expired. Ask the owner for a new one.")
    claim = db.get(Claim, h.claim_id)
    assert claim is not None
    item = claim.item
    if actor.role not in HANDOVER_ROLES and item.owner_id != actor.id:
        raise ApiError(403, "forbidden", "Only the finder or the desk can complete a handover.")
    if claim.status not in ("approved", "auto_approved"):
        raise ApiError(409, "claim_not_approved", "This claim isn't approved yet.")
    if (item.category == "id_card" or claim.verified_by == "roll_number") and not id_checked:
        raise ApiError(422, "id_check_required", "Check the college ID before handing this over, then confirm.", {"id_checked": "required"})

    now = datetime.now(timezone.utc)
    h.confirmed_at, h.confirmed_by, h.id_checked = now, actor.id, id_checked
    claim.status = "handed_over"
    item.status = "returned"
    lost = claim.match.lost_item if claim.match else None
    if lost is not None:
        lost.status = "returned"
    role = "desk" if actor.role != "student" else "finder"
    events.add_event(db, item.id, "handed_over", actor.id, role)
    if lost is not None:
        events.add_event(db, lost.id, "handed_over", actor.id, role)
    finder = db.get(User, item.owner_id)
    if finder is not None and finder.id != claim.claimant_id:
        finder.points += get_settings().finder_points
        notify(db, finder.id, "item_returned", "Returned to its owner", f"Thank you. +{get_settings().finder_points} points.", f"/items/{item.id}", {"item_id": str(item.id)})
    notify(db, claim.claimant_id, "item_returned", "You have your item back", "The handover is complete.", f"/items/{lost.id}" if lost else f"/items/{item.id}", {"claim_id": str(claim.id)})
    db.commit()
    return claim, item
