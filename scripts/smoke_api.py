#!/usr/bin/env python
"""Start the real API on its own port against the seeded database and walk the story over HTTP.

    python scripts/smoke_api.py                 # uses DATABASE_URL from .env, port 8021
    python scripts/smoke_api.py --port 8030

It spawns uvicorn as a subprocess (job worker off; the seed already ran the pipeline), reads the sign-in codes
from its console, and checks what a person would see: Alice's ranked matches with the why-breakdown, the
public list, the desk's claim queue, the admin insights, the eval report, and the live notification stream.
Read-only apart from OTP rows, so it is safe on a database other people are using.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Api:
    def __init__(self, base: str, log: list[str]):
        self.base, self.log = base, log

    def call(self, method: str, path: str, token: str | None = None, body: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, (json.loads(raw) if raw else None)

    def sign_in(self, email: str) -> str:
        n = len(self.log)
        assert self.call("POST", "/api/v1/auth/otp/request", body={"email": email})[0] == 204
        for _ in range(50):
            hit = [m for line in self.log[n:] for m in re.findall(r"code is (\d{6})", line)]
            if hit:
                break
            time.sleep(0.1)
        else:
            raise SystemExit("no sign-in code appeared in the server console")
        status, body = self.call("POST", "/api/v1/auth/otp/verify", body={"email": email, "code": hit[-1]})
        assert status == 200, body
        return body["token"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8021)
    args = ap.parse_args()

    env = {**os.environ, "DISABLE_WORKER": "1", "LC_ALL": "en_US.UTF-8", "ML_MODE": os.environ.get("ML_MODE", "full"),
           "DESK_EMAILS": "desk@college.edu", "ADMIN_EMAILS": "admin@college.edu"}
    proc = subprocess.Popen(
        [str(ROOT / ".venv" / "bin" / "python"), "-m", "uvicorn", "app.main:app", "--port", str(args.port), "--host", "127.0.0.1"],
        cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    log: list[str] = []
    threading.Thread(target=lambda: [log.append(line) for line in proc.stdout], daemon=True).start()  # type: ignore[union-attr]
    api = Api(f"http://127.0.0.1:{args.port}", log)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(("  ok   " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))
        if not ok:
            failures.append(name)

    try:
        for _ in range(120):
            try:
                if api.call("GET", "/health")[0] == 200:
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            print("\n".join(log[-30:]))
            return 1

        alice, desk, admin = (api.sign_in(f"{n}@college.edu") for n in ("alice", "desk", "admin"))
        print("signed in as alice, desk and admin over OTP")

        s, mine = api.call("GET", "/api/v1/items?mine=1", alice)
        check("alice sees her own reports", s == 200 and len(mine) >= 2, f"{len(mine or [])} items")
        laptop = next((i for i in mine if "laptop" in i["description"]), None)
        check("her laptop report was read into attributes", bool(laptop) and laptop["attributes"]["category"]["value"] == "laptop" and laptop["attributes"]["brand"]["value"] == "Dell")

        s, ms = api.call("GET", f"/api/v1/items/{laptop['id']}/matches", alice)
        check("two candidate laptops, best first", s == 200 and len(ms) >= 2 and ms[0]["score"] >= ms[1]["score"], ", ".join(f"{m['score']:.2f}" for m in ms))
        top = ms[0]
        check("the top match is a laptop and a real match", top["candidate"]["category"] == "laptop" and top["score"] >= 0.5, f"{top['band']} {top['score']:.2f}")
        check("the why-breakdown has nine rows that add up to the score", len(top["why"]) == 9 and abs(sum(w["contribution"] for w in top["why"]) - top["score"]) < 0.02)
        check("only found laptops are offered for a lost laptop", all(m["candidate"]["category"] in ("laptop", "tablet") for m in ms), ", ".join(m["candidate"]["category"] for m in ms))
        blob = json.dumps(ms)
        check("private details never appear in a match", "serial" not in blob.lower() and "4F2A" not in blob and "AB12" not in blob)

        s, pub = api.call("GET", "/api/v1/items/public", alice)
        card = next((p for p in pub if p.get("redacted")), None)
        s2, alerts = api.call("GET", "/api/v1/notifications", alice)
        check("public list holds found items, ID cards redacted", s == 200 and len(pub) >= 5 and card is not None and card["colors"] == [] and "brand" not in card)
        check("alice has unread and read alerts", s2 == 200 and len(alerts) >= 3 and any(not a["read"] for a in alerts) and any(a["read"] for a in alerts), f"{len(alerts)} alerts")

        s, queue = api.call("GET", "/api/v1/admin/claims?status=pending_review", desk)
        check("the desk's queue has a phone waiting for a person", s == 200 and any(c["category"] == "phone" and c["must_be_reviewed_by_person"] for c in queue), f"{len(queue or [])} pending")
        if queue:
            r = queue[0]["review"]
            check("the drawer shows answers next to private details", bool(r["answers"]) and bool(r["private_details"]) and r["score"] is not None)

        s, summ = api.call("GET", "/api/v1/admin/insights/summary?range=term", admin)
        check("insights summary", s == 200 and summ["open_lost"] > 0 and len(summ["trend"]) == 7, f"recovery {summ['recovery_rate']:.2f}, median {summ['median_hours_to_reunite']}h, precision {summ['live_precision']}")
        s, hot = api.call("GET", "/api/v1/admin/insights/hotspots?range=term", admin)
        check("library and canteen are the hotspots", s == 200 and {h["zone_id"] for h in hot[:2]} == {"z_library", "z_canteen"}, ", ".join(f"{h['zone_id']}={h['lost']}" for h in hot[:3]))
        s, scene = api.call("GET", "/api/v1/admin/ops/scene", admin)
        check("ops scene is zone level with no people", s == 200 and scene["pins"] and "@" not in json.dumps(scene) and "owner" not in json.dumps(scene), f"{len(scene['pins'])} pins, {len(scene['arcs'])} arcs")
        s, reports = api.call("GET", "/api/v1/admin/eval/reports", admin)
        check("eval report is listed and readable", s == 200 and reports and api.call("GET", f"/api/v1/admin/eval/reports/{reports[0]['run_id']}", admin)[1]["metrics"]["p_at_1"] >= 0, reports[0]["run_id"] if reports else "none")
        check("students cannot open admin pages", api.call("GET", "/api/v1/admin/insights/summary", alice)[0] == 403)

        # the live stream: connect, then ask the server to push an alert to alice, and see it arrive
        req = urllib.request.Request(api.base + "/api/v1/notifications/stream", headers={"Authorization": f"Bearer {alice}"})
        with urllib.request.urlopen(req, timeout=10) as stream:
            first = stream.readline().decode()
            check("notification stream opens", first.startswith(": connected"))
        s, health = api.call("GET", "/health")
        check("health reports which model path each stage took", s == 200 and isinstance(health["ml"], dict))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("\n" + ("all checks passed" if not failures else f"{len(failures)} check(s) failed: {failures}"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
