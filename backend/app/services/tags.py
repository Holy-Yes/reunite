"""QR tags. The finder needs no account: they open the tag link, leave a note, and keep the thread id in
their browser to read the owner's reply. The owner is told through a normal notification."""
from __future__ import annotations

import secrets
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import ApiError
from ..models import Tag, TagMessage, TagThread, User
from .chat import mask_contact
from .events import iso
from .notify import notify

MAX_TAGS = 20
MAX_LEN = 500
FINDER_MESSAGES_PER_HOUR = 10
_hits: dict[str, list[float]] = {}


def reset_limits() -> None:
    _hits.clear()


def _limit(key: str) -> None:
    now = time.time()
    hits = [t for t in _hits.get(key, []) if now - t < 3600]
    if len(hits) >= FINDER_MESSAGES_PER_HOUR:
        raise ApiError(429, "too_many_messages", "That's a lot of messages. Try again in a while.", retry_after=int(3600 - (now - hits[0])))
    hits.append(now)
    _hits[key] = hits


def _clean(body: str) -> str:
    text = mask_contact(" ".join((body or "").split()))
    if not text:
        raise ApiError(422, "invalid_request", "Write a message first.", {"body": "required"})
    if len(text) > MAX_LEN:
        raise ApiError(422, "invalid_request", f"Keep it under {MAX_LEN} characters.", {"body": "too long"})
    return text


def create(db: Session, user: User, label: str) -> Tag:
    label = " ".join((label or "").split())[:80]
    if not label:
        raise ApiError(422, "invalid_request", "Give the tag a name, like 'blue keychain'.", {"label": "required"})
    if (db.scalar(select(func.count(Tag.id)).where(Tag.owner_id == user.id)) or 0) >= MAX_TAGS:
        raise ApiError(409, "too_many_tags", f"You can have up to {MAX_TAGS} tags.")
    tag = Tag(code=secrets.token_urlsafe(8).replace("-", "x").replace("_", "y")[:10], owner_id=user.id, label=label)
    db.add(tag)
    db.commit()
    return tag


def by_code(db: Session, code: str) -> Tag:
    tag = db.scalar(select(Tag).where(Tag.code == code))
    if tag is None or not tag.active:
        raise ApiError(404, "not_found", "This tag isn't active. Thank you for trying.")
    return tag


def owned(db: Session, user: User, tag_id: str) -> Tag:
    try:
        tag = db.get(Tag, uuid.UUID(tag_id))
    except ValueError:
        tag = None
    if tag is None or tag.owner_id != user.id:
        raise ApiError(404, "not_found", "That tag isn't here.")
    return tag


def _msgs(db: Session, thread: TagThread) -> list[dict]:
    rows = db.scalars(select(TagMessage).where(TagMessage.thread_id == thread.id).order_by(TagMessage.created_at))
    return [{"id": str(m.id), "sender": m.sender, "body": m.body, "at": iso(m.created_at)} for m in rows]


def thread_for_finder(db: Session, tag: Tag, thread_id: str) -> dict:
    try:
        th = db.get(TagThread, uuid.UUID(thread_id))
    except ValueError:
        th = None
    if th is None or th.tag_id != tag.id:
        raise ApiError(404, "not_found", "That conversation isn't here.")
    return {"thread_id": str(th.id), "messages": _msgs(db, th)}


def finder_says(db: Session, tag: Tag, body: str, thread_id: str | None, client: str) -> dict:
    _limit(f"{client}|{tag.code}")
    text = _clean(body)
    if thread_id:
        th = db.get(TagThread, uuid.UUID(thread_id)) if _is_uuid(thread_id) else None
        if th is None or th.tag_id != tag.id:
            raise ApiError(404, "not_found", "That conversation isn't here.")
    else:
        th = TagThread(tag_id=tag.id)
        db.add(th)
        db.flush()
    db.add(TagMessage(thread_id=th.id, sender="finder", body=text))
    notify(db, tag.owner_id, "tag_found", f"Someone found your {tag.label}", text[:120], "/tags", {"tag_id": str(tag.id)})
    db.commit()
    return thread_for_finder(db, tag, str(th.id))


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False


def owner_threads(db: Session, tag: Tag) -> list[dict]:
    out = []
    for th in db.scalars(select(TagThread).where(TagThread.tag_id == tag.id).order_by(TagThread.created_at.desc())):
        out.append({"thread_id": str(th.id), "messages": _msgs(db, th)})
    return out


def owner_says(db: Session, tag: Tag, thread_id: str, body: str) -> dict:
    th = db.get(TagThread, uuid.UUID(thread_id)) if _is_uuid(thread_id) else None
    if th is None or th.tag_id != tag.id:
        raise ApiError(404, "not_found", "That conversation isn't here.")
    db.add(TagMessage(thread_id=th.id, sender="owner", body=_clean(body)))
    db.commit()
    return {"thread_id": str(th.id), "messages": _msgs(db, th)}


def tag_out(db: Session, tag: Tag) -> dict:
    n = db.scalar(select(func.count(TagThread.id)).where(TagThread.tag_id == tag.id)) or 0
    return {"id": str(tag.id), "code": tag.code, "label": tag.label, "active": tag.active, "threads": n, "created_at": iso(tag.created_at)}
