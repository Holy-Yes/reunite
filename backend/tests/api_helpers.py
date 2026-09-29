from __future__ import annotations

import json

from app import jobs
from tests.helpers import png_bytes


class Session:
    """A signed-in test user."""

    def __init__(self, client, email: str, code_box: list):
        self.client, self.email = client, email
        assert client.post("/api/v1/auth/otp/request", json={"email": email}).status_code == 204
        r = client.post("/api/v1/auth/otp/verify", json={"email": email, "code": code_box[-1]})
        assert r.status_code == 200, r.text
        body = r.json()
        self.token, self.user = body["token"], body["user"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, path, **kw):
        return self.client.get("/api/v1" + path, headers=self.h, **kw)

    def post(self, path, **kw):
        return self.client.post("/api/v1" + path, headers=self.h, **kw)

    def patch(self, path, **kw):
        return self.client.patch("/api/v1" + path, headers=self.h, **kw)

    def report(self, kind, text, zone, start, end=None, *, photo=False, attributes=None, custody=None):
        data = {"kind": kind, "text": text, "zone_id": zone, "occurred_from": start, "occurred_to": end or start}
        if custody:
            data["custody_zone_id"] = custody
        if attributes is not None:
            data["attributes"] = json.dumps(attributes)
        files = [("photos", ("thing.png", png_bytes((30, 30, 32)), "image/png"))] if photo else None
        r = self.post("/items", data=data, files=files)
        assert r.status_code == 201, r.text
        return r.json()
