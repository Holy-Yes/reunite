from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..errors import ApiError
from ..models import Item, Match, User
from ..services.serializers import match_out

router = APIRouter(tags=["matches"])


class Feedback(BaseModel):
    verdict: Literal["mine", "not_mine", "unsure"]


@router.get("/matches")
def my_matches(status: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = (
        select(Match)
        .join(Item, Item.id == Match.lost_item_id)
        .where(Item.owner_id == user.id, Item.status.in_(("open", "matched")), Match.score >= get_settings().min_show)
        .order_by(Match.score.desc())
    )
    if status == "pending":
        stmt = stmt.where(Match.feedback.is_(None))
    return [match_out(m) for m in db.scalars(stmt) if m.found_item.status in ("open", "matched", "claimed")]


@router.post("/matches/{match_id}/feedback")
def feedback(match_id: str, body: Feedback, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    try:
        m = db.get(Match, uuid.UUID(match_id))
    except ValueError:
        m = None
    if m is None or m.lost_item.owner_id != user.id:
        raise ApiError(404, "not_found", "That match isn't here.")
    m.feedback, m.feedback_at = body.verdict, datetime.now(timezone.utc)
    db.commit()
    return match_out(m)
