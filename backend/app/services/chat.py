"""Relay chat for an approved claim. People appear as roles ("owner", "finder"), never as emails, and
anything that looks like a phone number or email address is masked before it is stored."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import STAFF_ROLES, Claim, Message, User
from .events import iso
from .notify import notify

OPEN_STATUSES = ("approved", "auto_approved", "handed_over")
MAX_LEN = 500
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


def mask_contact(text: str) -> str:
    """Keep contact details out of the thread: the handover happens at the desk, not by phone."""
    return _PHONE.sub("[number hidden]", _EMAIL.sub("[email hidden]", text))


def role_of(claim: Claim, user: User) -> str:
    if user.id == claim.claimant_id:
        return "owner"
    if user.id == claim.item.owner_id:
        return "finder"
    return "desk"


def _guard(claim: Claim, user: User) -> str:
    role = role_of(claim, user)
    if role == "desk" and user.role not in STAFF_ROLES:
        raise ApiError(404, "not_found", "That claim isn't here.")
    if claim.status not in OPEN_STATUSES:
        raise ApiError(403, "chat_locked", "Chat opens once the claim is approved.")
    return role


def out(m: Message, claim: Claim, viewer: User) -> dict:
    sender = "owner" if m.sender_id == claim.claimant_id else "finder" if m.sender_id == claim.item.owner_id else "desk"
    return {"id": str(m.id), "sender": sender, "mine": m.sender_id == viewer.id, "body": m.body, "at": iso(m.created_at)}


def thread(db: Session, claim: Claim, user: User) -> list[dict]:
    _guard(claim, user)
    rows = db.scalars(select(Message).where(Message.claim_id == claim.id).order_by(Message.created_at))
    return [out(m, claim, user) for m in rows]


def send(db: Session, claim: Claim, user: User, body: str) -> dict:
    role = _guard(claim, user)
    if role == "desk":
        raise ApiError(403, "forbidden", "Only the owner and the finder can send messages.")
    if claim.status == "handed_over":
        raise ApiError(409, "chat_closed", "The item has been handed over, so this thread is closed.")
    text = mask_contact(" ".join((body or "").split()))
    if not text:
        raise ApiError(422, "invalid_request", "Write a message first.", {"body": "required"})
    if len(text) > MAX_LEN:
        raise ApiError(422, "invalid_request", f"Keep it under {MAX_LEN} characters.", {"body": "too long"})
    m = Message(claim_id=claim.id, sender_id=user.id, body=text)
    db.add(m)
    db.flush()
    other = claim.item.owner_id if role == "owner" else claim.claimant_id
    notify(db, other, "chat_message", "New message about a found item", text[:120], f"/claims/{claim.id}/chat", {"claim_id": str(claim.id)})
    db.commit()
    return out(m, claim, user)
