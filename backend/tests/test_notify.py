import asyncio
import types

import pytest

from app.config import get_settings
from app.models import Notification, PushSubscription
from app.services import notify as N
from tests import factories as fx


def test_notify_writes_an_in_app_row_and_reaches_a_live_subscriber(db):
    u = fx.user(db, "a@x.edu")

    async def scenario():
        q = N.hub.subscribe(str(u.id))
        n = N.notify(db, u.id, "new_match", "A possible match", "See why", "/matches?item=1")
        got = await asyncio.wait_for(q.get(), timeout=2)
        N.hub.unsubscribe(str(u.id), q)
        return n, got

    n, got = asyncio.run(scenario())
    assert n.channels == ["in_app"] and n.read_at is None
    assert got["title"] == "A possible match" and got["href"] == "/matches?item=1" and got["read"] is False and got["type"] == "new_match"
    assert db.query(Notification).count() == 1


def test_publish_with_no_subscribers_is_a_no_op(db):
    u = fx.user(db, "a@x.edu")
    N.notify(db, u.id, "claim_update", "hello")            # must not raise with nobody listening
    assert db.query(Notification).count() == 1


def test_email_goes_to_the_console_backend_when_enabled(db, capsys):
    u = fx.user(db, "a@x.edu")
    u.notify_email = True
    db.commit()
    n = N.notify(db, u.id, "item_returned", "You have your item back", "The handover is complete.")
    assert "email" in n.channels
    out = capsys.readouterr().out
    assert "to=a@x.edu" in out and "You have your item back" in out


def test_web_push_is_skipped_without_vapid_keys_and_used_with_them(db, monkeypatch):
    u = fx.user(db, "a@x.edu")
    u.notify_push = True
    db.add(PushSubscription(user_id=u.id, endpoint="https://push.example/abc", p256dh="k", auth="a"))
    db.commit()
    assert "push" not in N.notify(db, u.id, "new_match", "t").channels           # no VAPID keys configured

    sent = []
    monkeypatch.setattr(get_settings(), "vapid_private_key", "priv")
    monkeypatch.setattr(get_settings(), "vapid_public_key", "pub")
    fake = types.SimpleNamespace(webpush=lambda **kw: sent.append(kw), WebPushException=Exception)
    monkeypatch.setitem(__import__("sys").modules, "pywebpush", fake)
    n = N.notify(db, u.id, "new_match", "Second")
    assert "push" in n.channels and sent[0]["subscription_info"]["endpoint"] == "https://push.example/abc"
    assert "Second" in sent[0]["data"] and sent[0]["vapid_claims"]["sub"].startswith("mailto:")


def test_a_gone_push_subscription_is_removed(db, monkeypatch):
    u = fx.user(db, "a@x.edu")
    u.notify_push = True
    db.add(PushSubscription(user_id=u.id, endpoint="https://push.example/dead", p256dh="k", auth="a"))
    db.commit()
    monkeypatch.setattr(get_settings(), "vapid_private_key", "priv")
    monkeypatch.setattr(get_settings(), "vapid_public_key", "pub")

    class Gone(Exception):
        response = types.SimpleNamespace(status_code=410)

    def boom(**kw):
        raise Gone("gone")

    monkeypatch.setitem(__import__("sys").modules, "pywebpush", types.SimpleNamespace(webpush=boom, WebPushException=Gone))
    n = N.notify(db, u.id, "new_match", "t")
    db.commit()
    assert "push" not in n.channels and db.query(PushSubscription).count() == 0      # the browser dropped it: forget it


def test_a_failing_email_never_breaks_the_caller(db, monkeypatch):
    u = fx.user(db, "a@x.edu")
    u.notify_email = True
    db.commit()
    monkeypatch.setattr(get_settings(), "email_backend", "smtp")
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.invalid")
    n = N.notify(db, u.id, "new_match", "t")
    assert n.channels == ["in_app"]


def test_sse_endpoint_streams_a_notification(client, db, monkeypatch):
    """The stream needs the Authorization header (EventSource cannot send one, so clients use fetch)."""
    assert client.get("/api/v1/notifications/stream").status_code == 401
