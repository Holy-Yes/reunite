from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import Tag, User
from ..services import tags as svc

router = APIRouter(tags=["tags"])


class NewTag(BaseModel):
    label: str


class Body(BaseModel):
    body: str
    thread_id: str | None = None


class TagPatch(BaseModel):
    active: bool


# ---- the owner (signed in) ----------------------------------------------------------------

@router.post("/tags", status_code=201)
def create_tag(body: NewTag, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return svc.tag_out(db, svc.create(db, user, body.label))


@router.get("/tags")
def my_tags(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return [svc.tag_out(db, t) for t in db.scalars(select(Tag).where(Tag.owner_id == user.id).order_by(Tag.created_at.desc()))]


@router.patch("/tags/{tag_id}")
def patch_tag(tag_id: str, body: TagPatch, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    tag = svc.owned(db, user, tag_id)
    tag.active = body.active
    db.commit()
    return svc.tag_out(db, tag)


@router.get("/tags/{tag_id}/threads")
def tag_threads(tag_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    return svc.owner_threads(db, svc.owned(db, user, tag_id))


@router.post("/tags/{tag_id}/threads/{thread_id}/reply")
def reply(tag_id: str, thread_id: str, body: Body, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return svc.owner_says(db, svc.owned(db, user, tag_id), thread_id, body.body)


# ---- the finder (no account) --------------------------------------------------------------

@router.get("/public/tags/{code}")
def public_tag(code: str, db: Session = Depends(get_db)) -> dict:
    """Only the label. Nothing about who owns it."""
    return {"label": svc.by_code(db, code).label}


@router.post("/public/tags/{code}/messages", status_code=201)
def finder_message(code: str, body: Body, request: Request, db: Session = Depends(get_db)) -> dict:
    client = request.client.host if request.client else "unknown"
    return svc.finder_says(db, svc.by_code(db, code), body.body, body.thread_id, client)


@router.get("/public/tags/{code}/threads/{thread_id}")
def finder_thread(code: str, thread_id: str, db: Session = Depends(get_db)) -> dict:
    return svc.thread_for_finder(db, svc.by_code(db, code), thread_id)
