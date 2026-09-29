from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..errors import ApiError
from ..models import Claim, Handover, Item, User
from ..services import chat, claims as svc, handover as handover_svc
from ..services.events import iso
from ..services.notify import notify
from ..services.serializers import claim_out
from ..services.trust import trust_for
from datetime import datetime, timezone

router = APIRouter(tags=["claims"])


class ClaimCreate(BaseModel):
    match_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None  # ID cards only: the roll number is the proof


class Answer(BaseModel):
    question_id: str
    answer: str


class AnswerBody(BaseModel):
    answers: list[Answer]


class Decision(BaseModel):
    decision: Literal["approve", "reject", "more_info"]
    note: str | None = None


class MessageBody(BaseModel):
    body: str


class TipBody(BaseModel):
    amount: int
    note: str | None = None


class Confirm(BaseModel):
    code: str | None = None
    token: str | None = None
    id_checked: bool = False


def _claim(db: Session, claim_id: str, user: User) -> Claim:
    try:
        c = db.get(Claim, uuid.UUID(claim_id))
    except ValueError:
        c = None
    if c is None or not (c.claimant_id == user.id or c.item.owner_id == user.id or user.role in ("desk", "admin")):
        raise ApiError(404, "not_found", "That claim isn't here.")
    return c


def _view(c: Claim, user: User, db: Session | None = None) -> dict:
    is_reviewer = (c.item.owner_id == user.id) or (user.role in ("desk", "admin")) or (c.claimant_id == user.id)
    out = claim_out(c, staff=is_reviewer)
    if db is not None:
        out["chat_open"] = c.status in chat.OPEN_STATUSES
        other = db.get(User, c.item.owner_id if c.claimant_id == user.id else c.claimant_id)
        if other is not None and other.id != user.id:
            out["counterpart"] = {"role": "finder" if c.claimant_id == user.id else "owner", "trust": trust_for(db, other)}
        h = db.scalar(select(Handover).where(Handover.claim_id == c.id))
        if h is not None and h.tip_amount:
            out["tip"] = {"amount": h.tip_amount, "note": h.tip_note, "at": iso(h.tip_at)}
    return out


@router.post("/claims", status_code=201)
def create_claim(body: ClaimCreate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _view(svc.create_claim(db, user, body.match_id, body.item_id), user, db)


@router.post("/claims/{claim_id}/answers")
def answer(claim_id: str, body: AnswerBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = _claim(db, claim_id, user)
    if c.claimant_id != user.id:
        raise ApiError(403, "forbidden", "Only the person claiming can answer.")
    return _view(svc.submit_answers(db, c, [a.model_dump() for a in body.answers]), user, db)


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _view(_claim(db, claim_id, user), user, db)


@router.get("/claims")
def list_claims(role: Literal["claimant", "finder"] | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Claim).join(Item, Item.id == Claim.item_id)
    mine_as_claimant, mine_as_finder = Claim.claimant_id == user.id, Item.owner_id == user.id
    stmt = stmt.where(mine_as_claimant if role == "claimant" else mine_as_finder if role == "finder" else or_(mine_as_claimant, mine_as_finder))
    return [_view(c, user, db) for c in db.scalars(stmt.order_by(Claim.created_at.desc()).limit(200))]


@router.post("/claims/{claim_id}/decision")
def decide(claim_id: str, body: Decision, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = _claim(db, claim_id, user)
    return _view(svc.decide(db, c, user, body.decision, body.note), user, db)


def _handover_claim(db: Session, claim_id: str, user: User) -> Claim:
    c = _claim(db, claim_id, user)
    if c.claimant_id != user.id:
        raise ApiError(403, "forbidden", "The handover pass belongs to the person claiming.")
    if c.status not in ("approved", "auto_approved"):
        raise ApiError(409, "claim_not_approved", "This claim isn't approved yet.")
    return c


@router.get("/claims/{claim_id}/handover")
def get_handover(claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    c = _handover_claim(db, claim_id, user)
    h = db.scalar(select(Handover).where(Handover.claim_id == c.id))
    if h is None:
        h = handover_svc.issue(db, c)
        db.commit()
    return handover_svc.payload(c, h)


@router.post("/claims/{claim_id}/handover")
def reissue_handover(claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Get a new code after the old one expired."""
    c = _handover_claim(db, claim_id, user)
    h = handover_svc.issue(db, c)
    db.commit()
    return handover_svc.payload(c, h)


@router.post("/handover/confirm")
def confirm_handover(body: Confirm, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    claim, item = handover_svc.confirm(db, user, body.code, body.token, body.id_checked)
    from ..services.serializers import item_out

    return {"claim": claim_out(claim, staff=True), "item": item_out(db, item)}


@router.get("/claims/{claim_id}/messages")
def get_messages(claim_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return chat.thread(db, _claim(db, claim_id, user), user)


@router.post("/claims/{claim_id}/messages", status_code=201)
def post_message(claim_id: str, body: MessageBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return chat.send(db, _claim(db, claim_id, user), user, body.body)


@router.post("/claims/{claim_id}/tip")
def pledge_tip(claim_id: str, body: TipBody, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """A thank-you the owner pledges to hand over in person. Recorded only; no money moves through this app."""
    c = _claim(db, claim_id, user)
    if c.claimant_id != user.id:
        raise ApiError(403, "forbidden", "Only the person who got the item back can say thanks.")
    h = db.scalar(select(Handover).where(Handover.claim_id == c.id))
    if h is None or h.confirmed_at is None:
        raise ApiError(409, "not_returned", "You can say thanks once the handover is done.")
    if h.tip_amount:
        raise ApiError(409, "tip_exists", "You already said thanks for this one.")
    if not 1 <= body.amount <= 5000:
        raise ApiError(422, "invalid_request", "Pick an amount between 1 and 5000.", {"amount": "1 to 5000"})
    h.tip_amount, h.tip_note, h.tip_at = body.amount, (body.note or "").strip()[:300] or None, datetime.now(timezone.utc)
    notify(db, c.item.owner_id, "tip_pledged", "Someone wants to say thanks", f"They pledged {body.amount} for returning their item. Settle it in person if you both like.", f"/items/{c.item_id}", {"claim_id": str(c.id)})
    db.commit()
    return _view(c, user, db)
