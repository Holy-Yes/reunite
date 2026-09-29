"""QR tags: a finder with no account can reach the owner, and only the owner can see the thread list."""
import pytest

from app.services import tags as tags_svc
from tests.api_helpers import Session


@pytest.fixture()
def people(client, db, monkeypatch):
    codes: list[str] = []
    monkeypatch.setattr("app.api.auth.send_email", lambda to, subject, body: codes.append(body.split("code is ")[1][:6]) or True)
    p = type("P", (), {})()
    p.client = client
    p.owner = Session(client, "owner@college.edu", codes)
    p.other = Session(client, "other@college.edu", codes)
    return p


def test_owner_creates_a_tag_and_finder_reaches_them_without_an_account(people):
    tag = people.owner.post("/tags", json={"label": "  blue   keychain "}).json()
    assert tag["label"] == "blue keychain" and len(tag["code"]) == 10 and tag["threads"] == 0

    pub = people.client.get(f"/api/v1/public/tags/{tag['code']}")
    assert pub.status_code == 200 and pub.json() == {"label": "blue keychain"}       # nothing about the owner

    sent = people.client.post(f"/api/v1/public/tags/{tag['code']}/messages", json={"body": "Found it at the canteen, call 98765 43210"})
    assert sent.status_code == 201
    th = sent.json()
    assert "98765" not in th["messages"][0]["body"] and th["messages"][0]["sender"] == "finder"

    alerts = people.owner.get("/notifications").json()
    assert alerts[0]["type"] == "tag_found" and "blue keychain" in alerts[0]["title"]

    threads = people.owner.get(f"/tags/{tag['id']}/threads").json()
    assert len(threads) == 1 and threads[0]["thread_id"] == th["thread_id"]

    r = people.owner.post(f"/tags/{tag['id']}/threads/{th['thread_id']}/reply", json={"body": "Thank you! I'll come now."})
    assert r.status_code == 200 and [m["sender"] for m in r.json()["messages"]] == ["finder", "owner"]

    seen = people.client.get(f"/api/v1/public/tags/{tag['code']}/threads/{th['thread_id']}").json()
    assert [m["sender"] for m in seen["messages"]] == ["finder", "owner"]

    again = people.client.post(f"/api/v1/public/tags/{tag['code']}/messages", json={"body": "Where should I leave it?", "thread_id": th["thread_id"]})
    assert again.status_code == 201 and len(again.json()["messages"]) == 3


def test_other_users_cannot_read_or_reply_to_someone_elses_tag(people):
    tag = people.owner.post("/tags", json={"label": "laptop bag"}).json()
    th = people.client.post(f"/api/v1/public/tags/{tag['code']}/messages", json={"body": "hello"}).json()
    assert people.other.get(f"/tags/{tag['id']}/threads").status_code == 404
    assert people.other.post(f"/tags/{tag['id']}/threads/{th['thread_id']}/reply", json={"body": "x"}).status_code == 404
    assert people.client.get(f"/api/v1/tags").status_code == 401
    assert people.other.get("/tags").json() == []


def test_a_thread_id_from_another_tag_does_not_work(people):
    a = people.owner.post("/tags", json={"label": "keys"}).json()
    b = people.owner.post("/tags", json={"label": "bag"}).json()
    th = people.client.post(f"/api/v1/public/tags/{a['code']}/messages", json={"body": "hi"}).json()
    assert people.client.get(f"/api/v1/public/tags/{b['code']}/threads/{th['thread_id']}").status_code == 404
    assert people.client.post(f"/api/v1/public/tags/{b['code']}/messages", json={"body": "hi", "thread_id": th["thread_id"]}).status_code == 404
    assert people.client.get(f"/api/v1/public/tags/{a['code']}/threads/not-a-uuid").status_code == 404


def test_deactivated_and_unknown_tags_are_gone(people):
    tag = people.owner.post("/tags", json={"label": "keys"}).json()
    assert people.owner.patch(f"/tags/{tag['id']}", json={"active": False}).json()["active"] is False
    assert people.client.get(f"/api/v1/public/tags/{tag['code']}").status_code == 404
    assert people.client.post(f"/api/v1/public/tags/{tag['code']}/messages", json={"body": "hi"}).status_code == 404
    assert people.client.get("/api/v1/public/tags/nope").status_code == 404


def test_finder_messages_are_rate_limited_and_validated(people):
    tag = people.owner.post("/tags", json={"label": "keys"}).json()
    url = f"/api/v1/public/tags/{tag['code']}/messages"
    assert people.client.post(url, json={"body": "  "}).status_code == 422
    assert people.client.post(url, json={"body": "x" * 700}).status_code == 422
    for _ in range(tags_svc.FINDER_MESSAGES_PER_HOUR - 2):
        assert people.client.post(url, json={"body": "hi"}).status_code == 201
    assert people.client.post(url, json={"body": "hi"}).status_code == 429


def test_tag_needs_a_name_and_has_a_cap(people):
    assert people.owner.post("/tags", json={"label": "   "}).status_code == 422
    for i in range(tags_svc.MAX_TAGS):
        assert people.owner.post("/tags", json={"label": f"t{i}"}).status_code == 201
    assert people.owner.post("/tags", json={"label": "one more"}).status_code == 409
