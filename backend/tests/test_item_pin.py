"""A map pin on a report: the exact spot, private to the owner, and enough on its own to pick the place."""
import pytest

from tests.api_helpers import Session


@pytest.fixture()
def people(client, monkeypatch):
    codes: list[str] = []
    monkeypatch.setattr("app.api.auth.send_email", lambda to, subject, body: codes.append(body.split("code is ")[1][:6]) or True)
    return Session(client, "pin@college.edu", codes), Session(client, "other@college.edu", codes)


def post(s, **extra):
    data = {"kind": "lost", "text": "black backpack", "occurred_from": "2026-09-21T09:00:00Z", **extra}
    return s.post("/items", data=data)


def test_pin_alone_picks_the_nearest_zone(people):
    a, _ = people
    r = post(a, lat="17.54066", lon="78.38545")  # on the sports complex
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["zone_id"] == "z_sports"
    assert (body["lat"], body["lon"]) == (17.54066, 78.38545)


def test_explicit_zone_wins_and_pin_is_kept(people):
    a, _ = people
    body = post(a, zone_id="z_library", lat="17.54066", lon="78.38545").json()
    assert body["zone_id"] == "z_library" and body["lat"] == 17.54066


def test_bad_pins_are_rejected(people):
    a, _ = people
    assert post(a, zone_id="z_library", lat="17.5").status_code == 422          # one half of a pair
    assert post(a, zone_id="z_library", lat="abc", lon="78.3").status_code == 422
    assert post(a, zone_id="z_library", lat="95", lon="78.3").status_code == 422


def test_exact_pin_is_not_public(people):
    a, b = people
    found = a.post("/items", data={"kind": "found", "text": "black backpack", "zone_id": "z_library", "custody_zone_id": "z_gate", "occurred_from": "2026-09-21T09:00:00Z", "lat": "17.5372", "lon": "78.3863"}).json()
    public = b.get("/items/public").json()
    assert all("lat" not in i and "lon" not in i for i in public)
    assert b.get(f"/items/{found['id']}").status_code in (403, 404)
