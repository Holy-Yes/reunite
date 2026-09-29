"""A plain, explainable trust score from what a person has actually done here. No new table."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Claim, Handover, Item, User

BASE = 50  # a verified college email


def trust_for(db: Session, user: User) -> dict:
    returns = db.scalar(
        select(func.count(Handover.id)).join(Claim, Claim.id == Handover.claim_id).join(Item, Item.id == Claim.item_id).where(Item.owner_id == user.id, Handover.confirmed_at.is_not(None))
    ) or 0
    approved = db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == user.id, Claim.status.in_(("approved", "auto_approved", "handed_over")))) or 0
    rejected = db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == user.id, Claim.status == "rejected")) or 0
    score = BASE + min(30, 6 * returns) + min(12, 4 * approved) - 15 * min(rejected, 3)
    score = max(0, min(100, score))
    history = returns + approved + rejected
    level = "new" if history == 0 else "trusted" if score >= 70 else "ok" if score >= 40 else "low"
    return {"score": score, "level": level, "items_returned": returns, "claims_approved": approved, "claims_rejected": rejected, "points": user.points}
