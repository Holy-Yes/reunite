from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.models import OtpCode


@pytest.fixture()
def codes(monkeypatch):
    box: list[str] = []
    monkeypatch.setattr("app.api.auth.send_email", lambda to, subject, body: box.append(body.split("code is ")[1][:6]) or True)
    return box


def test_otp_sign_in_flow(client, codes):
    assert client.post("/api/v1/auth/otp/request", json={"email": "Ana@College.edu"}).status_code == 204
    r = client.post("/api/v1/auth/otp/verify", json={"email": "ana@college.edu", "code": codes[-1]})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "ana@college.edu" and body["user"]["role"] == "student"
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["email"] == "ana@college.edu"
    # the code is single use
    again = client.post("/api/v1/auth/otp/verify", json={"email": "ana@college.edu", "code": codes[-1]})
    assert again.status_code == 400


def test_wrong_code_message_and_lockout(client, codes):
    client.post("/api/v1/auth/otp/request", json={"email": "b@college.edu"})
    for i in range(5):
        r = client.post("/api/v1/auth/otp/verify", json={"email": "b@college.edu", "code": "000000"})
        assert r.status_code == 400
        assert r.json()["error"]["message"] == "That code doesn't match. Check the latest email."
    r = client.post("/api/v1/auth/otp/verify", json={"email": "b@college.edu", "code": codes[-1]})
    assert r.status_code == 429 and r.headers["Retry-After"]


def test_expired_code(client, codes, db):
    client.post("/api/v1/auth/otp/request", json={"email": "c@college.edu"})
    otp = db.query(OtpCode).one()
    otp.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.post("/api/v1/auth/otp/verify", json={"email": "c@college.edu", "code": codes[-1]}).status_code == 400


def test_request_rate_limit(client, codes):
    for _ in range(5):
        assert client.post("/api/v1/auth/otp/request", json={"email": "d@college.edu"}).status_code == 204
    r = client.post("/api/v1/auth/otp/request", json={"email": "d@college.edu"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "3600"


def test_domain_rule_and_bad_email(client, codes, monkeypatch):
    assert client.post("/api/v1/auth/otp/request", json={"email": "nope"}).status_code == 422
    monkeypatch.setattr(get_settings(), "allowed_email_domains", "college.edu")
    r = client.post("/api/v1/auth/otp/request", json={"email": "x@gmail.com"})
    assert r.status_code == 422 and "college email" in r.json()["error"]["message"]
    assert client.post("/api/v1/auth/otp/request", json={"email": "x@college.edu"}).status_code == 204


def test_bootstrap_roles_from_env(client, codes, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_emails", "boss@college.edu")
    monkeypatch.setattr(get_settings(), "desk_emails", "front@college.edu")
    monkeypatch.setattr(get_settings(), "security_guard_emails", "gate@college.edu")
    for email, role in (("boss@college.edu", "admin"), ("front@college.edu", "desk"), ("gate@college.edu", "security_guard"), ("kid@college.edu", "student")):
        client.post("/api/v1/auth/otp/request", json={"email": email})
        assert client.post("/api/v1/auth/otp/verify", json={"email": email, "code": codes[-1]}).json()["user"]["role"] == role


def test_unauthenticated_and_bad_token(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_roll_number_rules(client, codes):
    from tests.api_helpers import Session

    a, b = Session(client, "a@college.edu", codes), Session(client, "b@college.edu", codes)
    assert a.patch("/me", json={"roll_no": "21071a0542"}).json()["roll_no"] == "21071A0542"
    assert b.patch("/me", json={"roll_no": "21071A0542"}).status_code == 409
    assert b.patch("/me", json={"roll_no": "nonsense"}).status_code == 422
    assert a.patch("/me", json={"notify_email": True}).json()["notify_email"] is True


def test_demo_otp_fixes_the_code_and_is_advertised(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_otp", "123456")
    assert client.get("/api/v1/auth/config").json() == {"demo_otp": "123456"}
    assert client.post("/api/v1/auth/otp/request", json={"email": "demo@college.edu"}).status_code == 204
    r = client.post("/api/v1/auth/otp/verify", json={"email": "demo@college.edu", "code": "123456"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "demo@college.edu"


def test_no_demo_code_by_default(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_otp", "")
    assert client.get("/api/v1/auth/config").json() == {"demo_otp": None}
