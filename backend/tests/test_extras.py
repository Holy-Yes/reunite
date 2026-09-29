"""Relay chat, trust score, unclaimed routing, desk bulk logging and tip pledges."""
import uuid
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.models import Claim, Item
from app.services import chat, routing
from tests import factories as fx
from tests.test_api_flow import world  # noqa: F401  (fixture)


def approved_claim(world):  # noqa: F811
    m = world.a.get(f"/items/{world.lost['id']}/matches").json()[0]
    claim = world.a.post("/claims", json={"match_id": m["id"]}).json()
    stored = world.db.get(Claim, uuid.UUID(claim["id"]))
    answers = [{"question_id": q["id"], "answer": q["expected"]} for q in stored.questions]
    world.a.post(f"/claims/{claim['id']}/answers", json={"answers": answers})
    return claim["id"]


def test_chat_is_locked_until_the_claim_is_approved(world):
    cid = approved_claim(world)
    r = world.a.post(f"/claims/{cid}/messages", json={"body": "hi"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "chat_locked"
    assert world.b.get(f"/claims/{cid}/messages").status_code == 403
    world.b.post(f"/claims/{cid}/decision", json={"decision": "approve"})
    assert world.a.get(f"/claims/{cid}").json()["chat_open"] is True


def test_chat_relay_hides_contact_details_and_notifies(world):
    cid = approved_claim(world)
    world.b.post(f"/claims/{cid}/decision", json={"decision": "approve"})
    sent = world.a.post(f"/claims/{cid}/messages", json={"body": "Thanks! call me on +91 98765 43210 or mail alice@college.edu"})
    assert sent.status_code == 201
    body = sent.json()["body"]
    assert "98765" not in body and "@" not in body and "[number hidden]" in body and "[email hidden]" in body
    assert sent.json()["sender"] == "owner" and sent.json()["mine"] is True
    seen = world.b.get(f"/claims/{cid}/messages").json()
    assert len(seen) == 1 and seen[0]["sender"] == "owner" and seen[0]["mine"] is False
    assert "alice" not in str(seen)                                       # no identities in the thread
    assert any(n["type"] == "chat_message" for n in world.b.get("/notifications").json())
    assert world.a.post(f"/claims/{cid}/messages", json={"body": "   "}).status_code == 422
    assert world.a.post(f"/claims/{cid}/messages", json={"body": "x" * 700}).status_code == 422
    assert world.desk.get(f"/claims/{cid}/messages").status_code == 200      # staff can read
    assert world.desk.post(f"/claims/{cid}/messages", json={"body": "hello"}).status_code == 403


def test_chat_closes_after_handover_and_tip_is_recorded_once(world):
    cid = approved_claim(world)
    world.b.post(f"/claims/{cid}/decision", json={"decision": "approve"})
    assert world.a.post(f"/claims/{cid}/tip", json={"amount": 100}).status_code == 409   # not returned yet
    code = world.a.get(f"/claims/{cid}/handover").json()["code"]
    assert world.desk.post("/handover/confirm", json={"code": code}).status_code == 200
    assert world.a.post(f"/claims/{cid}/messages", json={"body": "thanks"}).json()["error"]["code"] == "chat_closed"
    assert world.b.post(f"/claims/{cid}/tip", json={"amount": 100}).status_code == 403   # only the owner pledges
    assert world.a.post(f"/claims/{cid}/tip", json={"amount": 0}).status_code == 422
    ok = world.a.post(f"/claims/{cid}/tip", json={"amount": 150, "note": "chai on me"})
    assert ok.status_code == 200 and ok.json()["tip"]["amount"] == 150
    assert world.a.post(f"/claims/{cid}/tip", json={"amount": 50}).status_code == 409
    assert any(n["type"] == "tip_pledged" for n in world.b.get("/notifications").json())


def test_trust_score_grows_with_returns_and_shows_on_the_claim(world):
    assert world.b.get("/users/me/trust").json()["level"] == "new"
    cid = approved_claim(world)
    cp = world.a.get(f"/claims/{cid}").json()["counterpart"]
    assert cp["role"] == "finder" and cp["trust"]["level"] == "new"
    world.b.post(f"/claims/{cid}/decision", json={"decision": "approve"})
    code = world.a.get(f"/claims/{cid}/handover").json()["code"]
    world.desk.post("/handover/confirm", json={"code": code})
    b = world.b.get("/users/me/trust").json()
    assert b["items_returned"] == 1 and b["score"] == 56 and b["level"] == "ok"
    a = world.a.get("/users/me/trust").json()
    assert a["claims_approved"] == 1 and a["score"] == 54
    assert world.a.get(f"/claims/{cid}").json()["counterpart"]["trust"]["items_returned"] == 1


def test_unclaimed_items_are_routed_to_the_desk(db):
    finder = fx.user(db, "f@x.edu")
    old = fx.item(db, finder, "found", "bottle")
    fresh = fx.item(db, finder, "found", "bottle")
    old.created_at = datetime.now(timezone.utc) - timedelta(days=get_settings().unclaimed_route_days + 1)
    old.custody_zone_id = "z_library"
    db.commit()
    assert routing.route_unclaimed(db) == 1
    db.refresh(old), db.refresh(fresh)
    assert old.routed_at and old.custody_zone_id == get_settings().unclaimed_route_zone and old.routed_to
    assert fresh.routed_at is None
    assert routing.route_unclaimed(db) == 0                                        # only once
    from app.services.events import timeline

    assert timeline(db, old.id)[-1]["type"] == "routed"


def test_item_with_an_open_claim_is_not_routed(db):
    finder, owner = fx.user(db, "f@x.edu"), fx.user(db, "o@x.edu")
    it = fx.item(db, finder, "found", "bottle")
    it.created_at = datetime.now(timezone.utc) - timedelta(days=90)
    db.add(Claim(item_id=it.id, claimant_id=owner.id, status="pending_review"))
    db.commit()
    assert routing.route_unclaimed(db) == 0


def test_desk_can_log_a_batch_of_found_items_students_cannot(world):
    rows = {"items": [{"text": "black umbrella", "zone_id": "z_canteen"}, {"text": "blue water bottle with sticker", "zone_id": "z_gate"}]}
    assert world.a.post("/items/bulk", json=rows).status_code == 403
    r = world.desk.post("/items/bulk", json=rows)
    assert r.status_code == 201 and r.json()["created"] == 2
    assert all(i["kind"] == "found" and i["custody_zone_id"] for i in r.json()["items"])
    assert world.desk.post("/items/bulk", json={"items": []}).status_code == 422
    assert world.desk.post("/items/bulk", json={"items": [{"text": "x", "zone_id": "nowhere"}]}).status_code == 422
    assert world.desk.patch("/me", json={"venue": "Main Gate"}).json()["venue"] == "Main Gate"
    assert world.a.patch("/me", json={"venue": "x"}).status_code == 403


def test_admin_can_trigger_routing_students_cannot(world):
    assert world.a.post("/admin/maintenance/route-unclaimed").status_code == 403
    assert world.admin.post("/admin/maintenance/route-unclaimed").json() == {"routed": 0}


def test_mask_contact_leaves_normal_text_alone():
    assert chat.mask_contact("Meet at the gate at 5 pm, room 204") == "Meet at the gate at 5 pm, room 204"
    assert "[number hidden]" in chat.mask_contact("9876543210")
