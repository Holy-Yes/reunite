"""The whole story over HTTP: lost report, found report, match, claim, approval, handover, timeline."""
import json

import pytest

from app import jobs
from app.config import get_settings
from app.models import Claim, Notification
from tests.api_helpers import Session
from tests.helpers import png_bytes

LOST_TEXT = "black Dell laptop, small dent on the lid, crescent moon sticker"
FOUND_TEXT = "found a black Dell laptop, dent on the lid and a crescent moon sticker, serial ending 4F2A"


@pytest.fixture()
def world(client, db, monkeypatch):
    codes: list[str] = []
    monkeypatch.setattr("app.api.auth.send_email", lambda to, subject, body: codes.append(body.split("code is ")[1][:6]) or True)
    monkeypatch.setattr(get_settings(), "desk_emails", "desk@college.edu")
    monkeypatch.setattr(get_settings(), "admin_emails", "admin@college.edu")
    w = type("W", (), {})()
    w.client, w.db = client, db
    w.a = Session(client, "alice@college.edu", codes)
    w.b = Session(client, "bob@college.edu", codes)
    w.desk = Session(client, "desk@college.edu", codes)
    w.admin = Session(client, "admin@college.edu", codes)
    w.lost = w.a.report("lost", LOST_TEXT, "z_library", "2026-09-21T09:00:00Z", "2026-09-21T13:00:00Z")
    hidden = {"marks": [{"value": "sticker: crescent moon", "source": "text", "confidence": 0.95, "hidden": True}], "serial": {"value": "AB12-4F2A", "source": "user", "confidence": 1, "hidden": True}}
    w.found = w.b.report("found", FOUND_TEXT, "z_gate", "2026-09-21T15:00:00Z", photo=True, attributes=hidden, custody="z_gate")
    jobs.drain(db)
    return w


def test_created_items_start_processing_then_open(client, db, world):
    assert world.lost["status"] == "processing" and world.found["status"] == "processing"
    assert world.lost["ticket_no"].startswith("RU-L-") and world.found["ticket_no"].startswith("RU-F-")
    lost = world.a.get(f"/items/{world.lost['id']}").json()
    assert lost["status"] in ("open", "matched") and lost["attributes"]["category"]["value"] == "laptop"
    assert lost["attributes"]["brand"]["value"] == "Dell"
    found = world.b.get(f"/items/{world.found['id']}").json()
    assert found["photos"] and found["attributes"]["category"]["value"] == "laptop"


def test_match_has_a_why_breakdown_and_no_hidden_details(client, db, world):
    ms = world.a.get(f"/items/{world.lost['id']}/matches").json()
    assert len(ms) == 1
    m = ms[0]
    assert m["band"] in ("strong", "possible") and m["score"] >= 0.4 and m["rank"] == 1
    assert [w["key"] for w in m["why"]] == ["category", "color", "brand", "image", "text", "cross_modal", "marks", "zone", "time"]
    assert sum(w["contribution"] for w in m["why"]) == pytest.approx(m["score"], abs=0.01)
    cand = m["candidate"]
    assert set(cand) <= {"id", "ticket_no", "category", "colors", "brand", "zone_id", "found_at", "photo", "redacted"}
    assert cand["photo"]["blurred"] is True and cand["photo"]["url"].startswith("/media/public/")
    blob = json.dumps(m)
    assert "crescent" not in blob and "4F2A" not in blob and "sticker" not in blob.replace("Sticker", "")  # marks stay private
    assert world.a.get("/matches", params={"status": "pending"}).json()[0]["id"] == m["id"]


def test_owner_is_notified_of_the_match(client, db, world):
    alerts = world.a.get("/notifications").json()
    assert alerts and alerts[0]["type"] == "new_match" and alerts[0]["read"] is False
    assert alerts[0]["href"].startswith("/matches?item=")
    assert world.b.get("/notifications").json() == []        # finders aren't told who lost it
    world.a.post(f"/notifications/{alerts[0]['id']}/read")
    assert world.a.get("/notifications").json()[0]["read"] is True
    assert world.a.post("/notifications/read-all").status_code == 204


def test_full_claim_and_handover_journey(client, db, world):
    m = world.a.get(f"/items/{world.lost['id']}/matches").json()[0]
    r = world.a.post("/claims", json={"match_id": m["id"]})
    assert r.status_code == 201
    claim = r.json()
    assert claim["status"] == "draft" and 3 <= len(claim["questions"]) <= 4
    assert all(set(q) <= {"id", "prompt", "kind", "choices"} for q in claim["questions"])
    assert "review" not in claim                                # the claimant never sees the review block

    stored = db.get(Claim, __import__("uuid").UUID(claim["id"]))
    answers = [{"question_id": q["id"], "answer": q["expected"]} for q in stored.questions]
    done = world.a.post(f"/claims/{claim['id']}/answers", json={"answers": answers}).json()
    assert done["status"] == "pending_review" and done["must_be_reviewed_by_person"] is True   # laptops are always checked

    # the finder sees the answers next to their private details
    theirs = world.b.get("/claims", params={"role": "finder"}).json()[0]
    assert theirs["review"]["answers"] and theirs["review"]["private_details"]
    assert any(n["type"] == "claim_update" for n in world.b.get("/notifications").json())

    assert world.a.post(f"/claims/{claim['id']}/decision", json={"decision": "approve"}).status_code == 403   # can't approve your own claim
    assert world.b.post(f"/claims/{claim['id']}/decision", json={"decision": "approve", "note": "matches what I saw"}).json()["status"] == "approved"

    ho = world.a.get(f"/claims/{claim['id']}/handover").json()
    assert len(ho["code"]) == 6 and ho["qr_payload"] and ho["expired"] is False and ho["collect_zone_id"] == "z_gate"
    assert world.b.get(f"/claims/{claim['id']}/handover").status_code == 403       # the pass belongs to the claimant

    bad = world.desk.post("/handover/confirm", json={"code": "000000"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_code"
    ok = world.desk.post("/handover/confirm", json={"code": ho["code"]})
    assert ok.status_code == 200 and ok.json()["claim"]["status"] == "handed_over" and ok.json()["item"]["status"] == "returned"

    types = [e["type"] for e in world.a.get(f"/items/{world.lost['id']}/events").json()]
    assert types[0] == "reported" and types[-1] == "handed_over" and {"matched", "claimed", "verified"} <= set(types)
    assert world.b.get("/me").json()["points"] == get_settings().finder_points
    assert world.a.get(f"/items/{world.lost['id']}").json()["status"] == "returned"


def test_access_control(client, db, world):
    other = world.desk  # desk can see everything; a plain student cannot
    stranger = Session(world.client, "eve@college.edu", [])  if False else None
    assert world.b.get(f"/items/{world.lost['id']}").status_code == 404      # not their report
    assert world.a.get(f"/items/{world.found['id']}").status_code == 404
    assert world.desk.get(f"/items/{world.lost['id']}").status_code == 200
    assert world.a.get("/admin/insights/summary").status_code == 403
    assert world.a.get("/admin/claims").status_code == 403
    assert world.a.patch(f"/items/{world.found['id']}", json={"text": "x"}).status_code == 404
    assert world.b.patch(f"/items/{world.found['id']}", json={"text": "still a laptop"}).status_code == 200
    assert client.get("/api/v1/items").status_code == 401


def test_public_list_shows_found_items_without_private_details(client, db, world):
    listing = world.a.get("/items/public").json()
    assert len(listing) == 1 and listing[0]["id"] == world.found["id"]
    assert "attributes" not in listing[0] and "description" not in listing[0]
    assert world.a.get("/items/public", params={"category": "phone"}).json() == []
    assert len(world.a.get("/items/public", params={"q": "dell"}).json()) == 1
    assert world.a.get("/items/public", params={"zone_id": "z_canteen"}).json() == []


def test_public_photo_is_blurred_and_original_is_private(client, db, world):
    photo = world.b.get(f"/items/{world.found['id']}").json()["photos"][0]
    pub = client.get(f"/media/public/{photo['id']}.jpg")
    assert pub.status_code == 200 and pub.headers["content-type"] == "image/jpeg"
    assert client.get(photo["url"]).status_code == 401                          # originals need a token
    assert world.a.client.get(photo["url"], headers=world.a.h).status_code == 404   # and the right person
    assert world.b.client.get(photo["url"], headers=world.b.h).status_code == 200
    assert world.desk.client.get(photo["url"], headers=world.desk.h).status_code == 200


def test_edit_reruns_matching_and_close(client, db, world):
    lost = world.lost["id"]
    r = world.a.patch(f"/items/{lost}", json={"zone_id": "z_sports", "attributes": {"brand": {"value": "HP", "source": "user"}}})
    assert r.status_code == 200 and r.json()["status"] == "processing"
    jobs.drain(db)
    item = world.a.get(f"/items/{lost}").json()
    assert item["status"] in ("open", "matched") and item["attributes"]["brand"]["value"] == "HP" and item["zone_id"] == "z_sports"
    m = world.a.get(f"/items/{lost}/matches").json()
    assert next(w for w in m[0]["why"] if w["key"] == "brand")["state"] == "mismatch"   # HP vs Dell
    assert world.a.patch(f"/items/{lost}", json={"attributes": {"category": {"value": "spaceship", "source": "user"}}}).status_code == 422
    closed = world.a.post(f"/items/{lost}/close", json={"reason": "found it myself"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert world.a.post(f"/items/{lost}/close", json={}).status_code == 409
    assert world.a.get(f"/items/{lost}/events").json()[-1]["type"] == "closed"


def test_feedback(client, db, world):
    m = world.a.get(f"/items/{world.lost['id']}/matches").json()[0]
    assert world.a.post(f"/matches/{m['id']}/feedback", json={"verdict": "not_mine"}).json()["feedback"] == "not_mine"
    assert world.a.get("/matches", params={"status": "pending"}).json() == []
    assert world.b.post(f"/matches/{m['id']}/feedback", json={"verdict": "mine"}).status_code == 404
    assert world.a.post(f"/matches/{m['id']}/feedback", json={"verdict": "maybe"}).status_code == 422


def test_reference_endpoints(client, db, world):
    t = world.a.get("/taxonomy").json()
    assert len(t["categories"]) == 18 and len(t["colors"]) == 17 and {"dent", "sticker"} <= set(t["marks"])
    z = world.a.get("/zones").json()
    assert z["type"] == "FeatureCollection" and len(z["features"]) == 8 and z["graph"]["edges"]


def test_extract_preview(client, db, world):
    r = world.a.post("/items/extract-preview", data={"text": "navy blue umbrella, Nike", "kind": "found"})
    assert r.status_code == 200
    body = r.json()
    assert body["attributes"]["category"]["value"] == "umbrella" and body["attributes"]["brand"]["value"] == "Nike"
    assert set(body) >= {"attributes", "detections", "ocr_text"}
    assert world.a.post("/items/extract-preview", data={}).status_code == 422
    f = world.a.post("/items/extract-preview", data={"text": "laptop with a sticker", "kind": "found"}, files=[("photo", ("x.png", png_bytes(), "image/png"))])
    assert f.status_code == 200 and f.json()["attributes"]["marks"][0]["hidden"] is True     # private by default on found reports


def test_validation_errors_use_one_shape(client, db, world):
    r = world.a.post("/items", data={"kind": "lost", "text": "", "zone_id": "z_library"})
    assert r.status_code == 422 and set(r.json()["error"]) >= {"code", "message"}
    assert world.a.post("/items", data={"kind": "lost", "text": "a phone", "zone_id": "z_nowhere"}).json()["error"]["fields"]["zone_id"]
    bad = world.a.post("/items", data={"kind": "found", "text": "wallet", "zone_id": "z_gate"}, files=[("photos", ("x.png", b"not an image", "image/png"))])
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_image"


def test_admin_insights_and_ops_scene(client, db, world):
    for path in ("summary", "hotspots", "heatmap", "categories", "finders"):
        r = world.admin.get(f"/admin/insights/{path}", params={"range": "term"})
        assert r.status_code == 200, path
    s = world.admin.get("/admin/insights/summary", params={"range": "term"}).json()
    assert s["open_lost"] == 1 and s["open_found"] == 1 and len(s["trend"]) == 7
    hm = world.admin.get("/admin/insights/heatmap", params={"range": "term"}).json()
    assert len(hm) == 7 and all(len(row) == 24 for row in hm)
    assert world.admin.get("/admin/insights/summary", params={"range": "1y"}).status_code == 422
    scene = world.admin.get("/admin/ops/scene").json()
    text = json.dumps(scene)
    assert "owner" not in text and "@" not in text and "alice" not in text            # zone-level only, no people
    assert set(scene) >= {"pins", "arcs", "heat"} and scene["pins"]
    assert world.desk.get("/admin/claims").status_code == 200
    assert world.desk.get("/admin/insights/summary").status_code == 403


def test_health(client):
    assert client.get("/health").json()["ok"] is True
