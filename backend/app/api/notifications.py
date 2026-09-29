from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..errors import ApiError
from ..models import Notification, User
from ..services.notify import hub, notification_out

router = APIRouter(tags=["alerts"])
KEEPALIVE_SECONDS = 15


@router.get("/notifications")
def list_notifications(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100))
    return [notification_out(n) for n in rows]


@router.post("/notifications/read-all", status_code=204)
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_one(notification_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    try:
        n = db.get(Notification, uuid.UUID(notification_id))
    except ValueError:
        n = None
    if n is None or n.user_id != user.id:
        raise ApiError(404, "not_found", "That alert isn't here.")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=204)


@router.get("/notifications/stream")
async def stream(user: User = Depends(current_user)) -> StreamingResponse:
    """Server-sent events. The client reads this with fetch and an Authorization header (EventSource can't set one)."""
    uid = str(user.id)
    q = hub.subscribe(uid)

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=KEEPALIVE_SECONDS)
                    yield f"event: notification\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            hub.unsubscribe(uid, q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
