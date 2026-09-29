"""One place that tells people things: an in-app row, the live SSE stream, Web Push, and email."""
from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import threading
import uuid
from collections import defaultdict
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Notification, PushSubscription, User
from .events import iso

log = logging.getLogger("reunite.notify")
email_log = logging.getLogger("reunite.email")


class Hub:
    """In-process pub/sub for SSE. Publishing happens on worker threads, delivery on the event loop."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def subscribe(self, user_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._subs[user_id].add(q)
        return q

    def unsubscribe(self, user_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs[user_id].discard(q)

    def publish(self, user_id: str, payload: dict) -> None:
        with self._lock:
            queues, loop = list(self._subs.get(user_id, ())), self._loop
        if not queues or loop is None:
            return
        for q in queues:
            loop.call_soon_threadsafe(_put_nowait, q, payload)


def _put_nowait(q: asyncio.Queue, payload: dict) -> None:
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        pass


hub = Hub()


def notification_out(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "href": n.href,
        "read": n.read_at is not None,
        "at": iso(n.created_at),
    }


def notify(db: Session, user_id: uuid.UUID, type_: str, title: str, body: str = "", href: str = "/", data: dict | None = None) -> Notification:
    """Create the notification and fan it out. Failures in push or email never break the caller."""
    user = db.get(User, user_id)
    n = Notification(user_id=user_id, type=type_, title=title, body=body, href=href, data=data or {}, channels=["in_app"])
    db.add(n)
    db.flush()
    if user is not None:
        if user.notify_push and _push(db, user, n):
            n.channels = [*n.channels, "push"]
        if user.notify_email and _email(user, n):
            n.channels = [*n.channels, "email"]
    hub.publish(str(user_id), notification_out(n))
    return n


def _push(db: Session, user: User, n: Notification) -> bool:
    s = get_settings()
    if not (s.vapid_private_key and s.vapid_public_key):
        return False
    subs = list(db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)))
    sent = False
    for sub in subs:
        try:
            from pywebpush import WebPushException, webpush

            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=json.dumps({"title": n.title, "body": n.body, "href": n.href}),
                vapid_private_key=s.vapid_private_key,
                vapid_claims={"sub": s.vapid_subject},
            )
            sent = True
        except Exception as e:  # noqa: BLE001
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):  # the browser dropped the subscription
                db.delete(sub)
            log.warning("web push failed for %s: %s", user.email, e)
    return sent


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    if s.email_backend != "smtp" or not s.smtp_host:
        email_log.info("EMAIL to=%s subject=%s\n%s", to, subject, body)
        print(f"[email] to={to} subject={subject}\n{body}\n")
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_user or "reunite@localhost", to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, 587, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("smtp send failed: %s", e)
        return False


def _email(user: User, n: Notification) -> bool:
    return send_email(user.email, n.title, n.body or n.title)
