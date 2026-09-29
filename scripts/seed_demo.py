#!/usr/bin/env python
"""Seed the database with demo data that exercises the hostile cases in docs/WEBSITE_PROMPT.md section 7.

    python scripts/seed_demo.py --reset            # wipe and reseed (real models; photos need scripts/fetch_seed_photos.py)
    python scripts/seed_demo.py --reset --light    # tiny stand-in models, seconds instead of minutes

Sign in as any seeded address. With DEMO_OTP set (see .env) the code is that value; otherwise the backend console prints it.

    asha@vnrvjiet.ac.in     student, the "current user": a matched laptop, a phone still processing, QR tags with a live thread
    rahul@vnrvjiet.ac.in    finder (laptop, watch, ID card)
    charan@ / dev@ / farah@ / riya@vnrvjiet.ac.in   other students (riya has a roll number and a disputed laptop claim)
    desk@vnrvjiet.ac.in     desk (claims to review, handover confirmation)      admin@vnrvjiet.ac.in   admin (insights)
    guard@vnrvjiet.ac.in    security guard (handover confirmation only, scan or code -- no claims queue)

Every report carries a map pin inside its zone, so the campus map shows lost and found markers.
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("JWT_SECRET", "dev-secret-change-me")
if "--light" in sys.argv:
    os.environ["ML_MODE"] = "light"

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import db as dbmod, jobs  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import (  # noqa: E402
    AttributeLabel, Claim, Handover, Item, ItemEvent, ItemImage, Job, Match, Notification, OtpCode, PushSubscription, User, Zone,
)
from app.services import chat, claims, events, handover, items as items_svc, tags as tags_svc  # noqa: E402
from app.services.notify import notify  # noqa: E402
from app.services.zones import load_zones  # noqa: E402

PHOTOS = ROOT / "data" / "seed" / "photos"
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
rng = random.Random(11)


def ago(days: float = 0, hours: float = 0) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


# ---- helpers ----------------------------------------------------------------------------------


def photo(category: str, n: int = 1) -> bytes | None:
    p = PHOTOS / f"{category}_{n:02d}.jpg"
    return p.read_bytes() if p.exists() else None


def plate(label: str, rgb: tuple[int, int, int]) -> bytes:
    """A stand-in photo when the Open Images set has not been fetched."""
    im = Image.new("RGB", (640, 480), (240, 238, 234))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((120, 100, 520, 380), radius=24, fill=rgb)
    d.text((320, 240), label, fill=(245, 245, 245), anchor="mm", font=ImageFont.load_default(size=32))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def id_card_photo() -> bytes:
    """A printed-looking college ID with a roll number, so OCR has something real to read."""
    im = Image.new("RGB", (900, 560), (250, 250, 248))
    d = ImageDraw.Draw(im)
    big, mid, small = (ImageFont.load_default(size=s) for s in (46, 36, 28))
    d.rectangle((0, 0, 900, 110), fill=(20, 20, 20))
    d.text((40, 30), "COLLEGE IDENTITY CARD", fill=(255, 255, 255), font=big)
    d.rectangle((40, 150, 260, 420), fill=(200, 200, 205))
    d.text((300, 170), "RIYA SHARMA", fill=(10, 10, 10), font=big)
    d.text((300, 250), "Roll No: 21071A0542", fill=(10, 10, 10), font=mid)
    d.text((300, 310), "B.Tech Computer Science", fill=(60, 60, 60), font=small)
    d.text((300, 360), "Valid till 2025", fill=(60, 60, 60), font=small)
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def get_user(db, email: str, role: str = "student", roll_no: str | None = None) -> User:
    u = db.scalar(select(User).where(User.email == email))
    if u is None:
        u = User(email=email, role=role, roll_no=roll_no)
        db.add(u)
        db.flush()
    return u


ZONE_POS: dict[str, tuple[float, float]] = {}


def pin(db, zone: str) -> tuple[float, float]:
    """A believable spot inside a zone: its centre, nudged by up to ~25 m, so the map pins do not stack on one point."""
    if not ZONE_POS:
        ZONE_POS.update({z.id: (z.centroid_lat, z.centroid_lon) for z in db.scalars(select(Zone))})
    lat, lon = ZONE_POS[zone]
    return lat + rng.uniform(-0.00022, 0.00022), lon + rng.uniform(-0.00024, 0.00024)


def report(db, user, kind, text, zone, start, end=None, *, img: bytes | None = None, attrs=None, custody=None, created: datetime | None = None, enqueue=True) -> Item:
    lat, lon = pin(db, zone)
    item = items_svc.create_item(
        db, user, kind=kind, text=text, zone_id=zone, occurred_from=start, occurred_to=end or start,
        custody_zone_id=custody, attributes=attrs, photos=[img] if img else [], lat=lat, lon=lon,
    )
    if created:
        item.created_at = created
        for e in db.scalars(select(ItemEvent).where(ItemEvent.item_id == item.id)):
            e.at = created
    if enqueue:
        jobs.enqueue(db, "ingest", {"item_id": str(item.id)})
    db.commit()
    return item


def hide(*fields_and_values):
    return {}


def backdate_flow(db, item: Item, when: dict[str, datetime]) -> None:
    for e in db.scalars(select(ItemEvent).where(ItemEvent.item_id == item.id)):
        if e.type in when:
            e.at = when[e.type]
    db.commit()


def return_flow(db, lost: Item, found: Item, desk: User, timeline: dict[str, datetime]) -> Claim:
    """Run a real claim through the services (answers, approval, handover), then backdate its story."""
    m = db.scalar(select(Match).where(Match.lost_item_id == lost.id, Match.found_item_id == found.id))
    if m is None:
        m = Match(lost_item_id=lost.id, found_item_id=found.id, score=0.82, band="strong", rank=1, features=[], feedback="mine")
        db.add(m)
        db.commit()
    claimant = db.get(User, lost.owner_id)
    claim = claims.create_claim(db, claimant, m.id, None)
    answers = [{"question_id": q["id"], "answer": q["expected"]} for q in claim.questions]
    claim = claims.submit_answers(db, claim, answers)
    if claim.status == "pending_review":
        claim = claims.decide(db, claim, desk, "approve", "checked the sticker")
    h = db.scalar(select(Handover).where(Handover.claim_id == claim.id))
    code = handover.payload(claim, h)["code"]
    handover.confirm(db, desk, code, None, True)
    for it in (lost, found):
        backdate_flow(db, it, timeline)
    h = db.scalar(select(Handover).where(Handover.claim_id == claim.id))
    h.confirmed_at = timeline["handed_over"]
    m.created_at = timeline["matched"]
    lost.created_at = timeline["reported"]
    lost.updated_at = found.updated_at = timeline["handed_over"]
    db.commit()
    return claim


def wipe(db) -> None:
    """Delete every row, children before parents, following the schema itself so tables added later are covered."""
    from app import models  # noqa: F401  (make sure every table is registered on the metadata)

    for table in reversed(dbmod.Base.metadata.sorted_tables):
        if table.name != "alembic_version":
            db.execute(table.delete())
    db.commit()
    media = get_settings().media_path
    for sub in ("incoming", "original", "public"):
        for f in (media / sub).glob("*"):
            f.unlink(missing_ok=True)


# ---- the story --------------------------------------------------------------------------------


def seed(db) -> dict:
    load_zones(db)
    alice = get_user(db, "asha@vnrvjiet.ac.in")
    bob = get_user(db, "rahul@vnrvjiet.ac.in")
    chen = get_user(db, "charan@vnrvjiet.ac.in")
    dev = get_user(db, "dev@vnrvjiet.ac.in")
    farah = get_user(db, "farah@vnrvjiet.ac.in")
    riya = get_user(db, "riya@vnrvjiet.ac.in", roll_no="21071A0542")
    desk = get_user(db, "desk@vnrvjiet.ac.in", "desk")
    admin = get_user(db, "admin@vnrvjiet.ac.in", "admin")
    guard = get_user(db, "guard@vnrvjiet.ac.in", "security_guard")
    for u in (alice, dev, riya):
        u.notify_email = False
    db.commit()

    # 1-2. Alice's laptop, with two strong matches (Bob and Chen each turned one in)
    lost_laptop = report(db, alice, "lost", "black Dell laptop, small dent on the lid, crescent moon sticker", "z_library", ago(1, 5), ago(1, 1), created=ago(1, 4))
    report(db, bob, "found", "black laptop, small dent on the lid", "z_gate", ago(0, 20), img=photo("laptop", 1) or plate("laptop", (30, 30, 34)), custody="z_gate", created=ago(0, 19))
    found_laptop_chen = report(
        db, chen, "found", "black Dell laptop with a crescent moon sticker and a dent, serial ending 4F2A", "z_canteen", ago(0, 16),
        img=photo("laptop", 2) or plate("laptop", (36, 36, 40)), custody="z_gate", created=ago(0, 15),
        attrs={"marks": [{"value": "sticker: crescent moon", "source": "text", "confidence": 0.95, "hidden": True}], "serial": {"value": "AB12-4F2A", "source": "user", "confidence": 1, "hidden": True}},
    )

    # 3. a 30-word description at the longest zone name, to test truncation
    report(
        db, dev, "found",
        "Navy blue foldable umbrella with a curved wooden handle, a small brass tip, one bent rib on the left side and a torn strap, "
        "left on the bench at the college bus stop after the evening bus, looks fairly old but well kept",
        "z_bus", ago(1, 3), img=photo("umbrella", 1) or plate("umbrella", (31, 47, 85)), custody="z_bus", created=ago(1, 2),
    )

    # 4. text-only lost bottle, photo-only found bottle (cross-modal), and a photo-only found pair of headphones
    lost_bottle = report(db, dev, "lost", "blue steel water bottle, Milton", "z_canteen", ago(1, 6), ago(1, 4), created=ago(1, 5))
    found_bottle = report(db, farah, "found", "", "z_canteen", ago(1, 2), img=photo("bottle", 1) or plate("bottle", (47, 95, 184)), custody="z_gate", created=ago(1, 1))
    report(db, farah, "found", "", "z_block_b", ago(0, 9), img=photo("headphones", 1) or plate("headphones", (50, 50, 50)), custody="z_block_b", created=ago(0, 8))

    # 5. an ID card: roll number read by OCR, redacted publicly, owner notified directly
    report(db, bob, "found", "college ID card", "z_admin", ago(0, 6), img=id_card_photo(), custody="z_gate", created=ago(0, 5))

    # 6. low confidence: a bag with no brand and a vague description
    report(db, farah, "found", "a grey bag", "z_block_a", ago(0, 12), img=photo("backpack", 2) or plate("bag", (139, 144, 150)), custody="z_block_a", created=ago(0, 11))

    # 7. Alice's second lost item is still processing (no job queued)
    report(db, alice, "lost", "black phone with a cracked screen", "z_block_b", ago(0, 3), ago(0, 1), created=ago(0, 1), enqueue=False)

    # 8. nothing anywhere near this: zero matches
    report(db, farah, "lost", "Casio scientific calculator, scratched", "z_sports", ago(2, 4), ago(2, 2), created=ago(2, 3))

    # phone pair for the desk's claim queue (phones always go to a person)
    lost_phone = report(db, dev, "lost", "black Samsung phone, scratched back, crescent sticker", "z_library", ago(1, 8), ago(1, 5), created=ago(1, 7))
    found_phone = report(
        db, farah, "found", "black Samsung phone with a crescent sticker, serial ending 91C7", "z_library", ago(1, 3),
        img=photo("phone", 2) or plate("phone", (20, 20, 24)), custody="z_gate", created=ago(1, 2),
        attrs={"serial": {"value": "SM-91C7", "source": "user", "confidence": 1, "hidden": True}, "marks": [{"value": "sticker: crescent", "source": "user", "confidence": 1, "hidden": True}]},
    )

    # 9. a returned item with the full six-stop timeline
    lost_watch = report(db, chen, "lost", "silver Casio watch, engraved initials on the back", "z_sports", ago(4, 6), ago(4, 2), created=ago(4, 5))
    found_watch = report(
        db, bob, "found", "silver Casio watch with engraved initials", "z_sports", ago(3, 20), img=photo("watch", 1) or plate("watch", (195, 200, 205)), custody="z_gate", created=ago(3, 19),
        attrs={"marks": [{"value": "engraved", "source": "user", "confidence": 1, "hidden": True}]},
    )

    jobs.drain(db, limit=500)
    db.expire_all()      # the worker changed statuses on rows this session already holds
    for it in (found_bottle, found_phone, found_watch):
        print(f"  {it.ticket_no} {it.category} status={it.status}")

    # claims: one auto-approved (bottle), one waiting for a person (phone), then the returned watch
    bm = db.scalar(select(Match).where(Match.lost_item_id == lost_bottle.id, Match.found_item_id == found_bottle.id))
    if bm is None:
        bm = Match(lost_item_id=lost_bottle.id, found_item_id=found_bottle.id, score=0.7, band="possible", rank=1, features=[])
        db.add(bm)
        db.commit()
    bclaim = claims.create_claim(db, dev, bm.id, None)
    claims.submit_answers(db, bclaim, [{"question_id": q["id"], "answer": q["expected"]} for q in bclaim.questions])

    pm = db.scalar(select(Match).where(Match.lost_item_id == lost_phone.id, Match.found_item_id == found_phone.id))
    if pm is None:
        pm = Match(lost_item_id=lost_phone.id, found_item_id=found_phone.id, score=0.8, band="strong", rank=1, features=[])
        db.add(pm)
        db.commit()
    pclaim = claims.create_claim(db, dev, pm.id, None)
    claims.submit_answers(db, pclaim, [{"question_id": q["id"], "answer": q["expected"]} for q in pclaim.questions])

    extras(db, asha=alice, riya=riya, farah=farah, dev=dev, desk=desk, bottle_claim=bclaim, laptop=found_laptop_chen)

    return_flow(db, lost_watch, found_watch, desk, {"reported": ago(4, 5), "matched": ago(3, 18), "claimed": ago(3, 8), "verified": ago(3, 6), "handed_over": ago(3, 2)})

    history(db, desk)
    feedback_and_alerts(db, alice, lost_laptop)
    return {"users": 8, "items": db.query(Item).count(), "matches": db.query(Match).count(), "claims": db.query(Claim).count(), "notifications": db.query(Notification).count()}


def extras(db, *, asha: User, riya: User, farah: User, dev: User, desk: User, bottle_claim: Claim, laptop: Item) -> None:
    """The sections that need a story of their own: relay chat, QR tags, a disputed claim, an unclaimed item routed to the desk."""
    # relay chat on the approved bottle claim (dev owns the bottle, farah found it)
    chat.send(db, bottle_claim, dev, "Hi! That looks like my blue Milton bottle. Thank you so much for turning it in.")
    chat.send(db, bottle_claim, farah, "No problem. I left it at the main gate security desk, they have my note.")
    chat.send(db, bottle_claim, dev, "Great, I'll pick it up after the 3 pm lab. Should I show my ID?")
    chat.send(db, bottle_claim, farah, "Yes, the desk checks ID and the code on your handover pass.")

    # QR tags: one with a live conversation, one quiet, one switched off
    bag = tags_svc.create(db, asha, "Grey laptop bag")
    tags_svc.create(db, asha, "Bike keys, red keychain")
    old = tags_svc.create(db, asha, "Old hostel trunk")
    old.active = False
    db.commit()
    th = tags_svc.finder_says(db, bag, "Hi, I found a grey laptop bag with this tag on a bench near the library steps.", None, "demo")
    tags_svc.owner_says(db, bag, th["thread_id"], "Thank you so much! I'm in the library right now. Could you hand it to the security desk at the main gate?")
    tags_svc.finder_says(db, bag, "Sure, I'll walk it over now.", th["thread_id"], "demo")

    # a disputed claim: Riya says the laptop Charan found is hers, but her answers do not fit. It waits for the desk.
    lost = report(db, riya, "lost", "black laptop, lid has a sticker", "z_block_a", ago(1, 6), ago(1, 3), created=ago(1, 2))
    jobs.drain(db, limit=200)
    db.expire_all()
    m = db.scalar(select(Match).where(Match.lost_item_id == lost.id, Match.found_item_id == laptop.id))
    if m is None:
        m = Match(lost_item_id=lost.id, found_item_id=laptop.id, score=0.58, band="possible", rank=1, features=[])
        db.add(m)
        db.commit()
    try:
        disputed = claims.create_claim(db, riya, m.id, None)
        claims.submit_answers(db, disputed, [{"question_id": q["id"], "answer": ("z_sports" if q.get("kind") == "zone" else "not sure")} for q in disputed.questions])
        if disputed.status == "pending_review":
            claims.decide(db, disputed, desk, "more_info", "Can you describe the sticker, and where exactly on the lid it is?")
    except Exception as e:  # noqa: BLE001  (a rule blocked the second claim; the rest of the demo still stands)
        db.rollback()
        print("  skipped the disputed claim:", e)

    # an unclaimed found item that has been handed on to the security desk after 30 days
    stale = report(db, farah, "found", "green umbrella with a wooden handle", "z_block_b", ago(38), img=photo("umbrella", 2) or plate("umbrella", (40, 110, 60)), custody="z_gate", created=ago(37))
    stale.routed_at, stale.routed_to = ago(6), "the campus security desk"
    db.commit()


CATEGORY_MIX = [
    ("laptop", 5, ["black Dell laptop", "grey HP laptop with a sticker", "silver MacBook"]),
    ("phone", 6, ["blue Samsung phone", "black iPhone with a cracked screen", "white OnePlus phone"]),
    ("bottle", 6, ["steel water bottle", "green Cello bottle", "black flask"]),
    ("backpack", 5, ["black backpack", "red Wildcraft bag", "navy Skybags backpack"]),
    ("earbuds", 4, ["white earbuds in a case", "black boAt earbuds"]),
    ("id_card", 3, ["college ID card"]),
    ("charger", 3, ["white phone charger", "black laptop charger"]),
    ("book", 3, ["blue textbook", "thick physics book"]),
    ("keys", 2, ["bike keys with a red keychain"]),
    ("spectacles", 2, ["black spectacles", "silver glasses"]),
]
HOT_ZONES = ["z_library"] * 5 + ["z_canteen"] * 5 + ["z_block_a"] * 3 + ["z_block_b"] * 2 + ["z_gate"] * 2 + ["z_sports"] * 2 + ["z_bus"] * 2 + ["z_admin"]


def history(db, desk: User) -> None:
    """A week of activity so the insights and the ops replay have something to show: library and canteen are the hotspots."""
    students = [get_user(db, f"student{i}@vnrvjiet.ac.in") for i in range(1, 9)]
    lost_items: list[Item] = []
    for cat, count, phrases in CATEGORY_MIX:
        for _ in range(count):
            u = rng.choice(students)
            day = rng.uniform(0.3, 6.8)
            hour = rng.choice([9, 10, 11, 12, 13, 14, 15, 17])
            start = ago(day).replace(hour=hour)
            lost_items.append(report(db, u, "lost", rng.choice(phrases), rng.choice(HOT_ZONES), start, start + timedelta(hours=rng.uniform(1, 4)), created=start + timedelta(hours=5), enqueue=True))
    for it in lost_items[:20]:  # about half get turned in
        f_user = rng.choice(students)
        t = it.occurred_to + timedelta(hours=rng.uniform(1, 30))
        report(db, f_user, "found", it.description.replace("lost", ""), rng.choice([it.zone_id, it.zone_id, rng.choice(HOT_ZONES)]), min(t, NOW - timedelta(hours=1)), custody="z_gate", created=min(t, NOW - timedelta(hours=1)) + timedelta(minutes=30))
    jobs.drain(db, limit=1000)

    # a handful of completed returns (real claims through the services) so recovery rate and time-to-reunite are real numbers
    done = 0
    for it in lost_items:
        if done >= 5:
            break
        m = db.scalar(select(Match).where(Match.lost_item_id == it.id, Match.score >= 0.4).order_by(Match.score.desc()))
        if m is None or m.found_item.status not in ("open", "matched") or it.status not in ("open", "matched"):
            continue
        if (m.found_item.category or "") in get_settings().review_categories and (m.found_item.category == "id_card"):
            continue
        try:
            return_flow(db, it, m.found_item, desk, {"reported": it.created_at, "matched": it.created_at + timedelta(hours=2), "claimed": it.created_at + timedelta(hours=9), "verified": it.created_at + timedelta(hours=10), "handed_over": it.created_at + timedelta(hours=rng.uniform(12, 40))})
            done += 1
        except Exception as e:  # noqa: BLE001  (a claim rule blocked it; try the next pair)
            db.rollback()
            print("  skipped a history return:", e)


def feedback_and_alerts(db, alice: User, lost_laptop: Item) -> None:
    ms = list(db.scalars(select(Match).where(Match.feedback.is_(None)).order_by(Match.score.desc()).limit(60)))
    for i, m in enumerate(ms):
        if m.lost_item.owner_id == alice.id and m.lost_item_id == lost_laptop.id:
            continue  # leave Alice's deck untouched: she sees her matches fresh
        m.feedback = "mine" if (i % 5) < 3 else "not_mine"
        m.feedback_at = ago(rng.uniform(0, 5))
    for n in db.scalars(select(Notification).where(Notification.user_id == alice.id).order_by(Notification.created_at)):
        pass
    extra = [
        ("claim_update", "Your ID reminder", "Add your roll number to your profile so a lost ID card can find you.", "/me"),
        ("new_match", "A possible match for your phone", "Possible match, 46%. See why it fits.", "/matches"),
    ]
    for t, title, body, href in extra:
        n = notify(db, alice.id, t, title, body, href)
        n.created_at = ago(0, 6)
    ns = list(db.scalars(select(Notification).where(Notification.user_id == alice.id).order_by(Notification.created_at)))
    for n in ns[: max(len(ns) // 2, 1)]:
        n.read_at = ago(0, 2)
    db.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="delete existing data first")
    ap.add_argument("--light", action="store_true", help="use tiny stand-in models (fast; matches are not meaningful)")
    args = ap.parse_args()
    if dbmod.SessionLocal is None:
        dbmod.configure()
    from app.ml import registry

    registry.setup_cache_dirs()
    db = dbmod.SessionLocal()
    try:
        if db.scalar(select(User.id).limit(1)) and not args.reset:
            print("The database already has data. Use --reset to wipe and reseed.")
            return 1
        if args.reset:
            wipe(db)
        info = seed(db)
        print("seeded:", info)
        print("sign in as asha@vnrvjiet.ac.in (student), rahul@ (finder), desk@ (desk), guard@ (security guard) or admin@ (admin), all @vnrvjiet.ac.in. Demo code: 123456 when DEMO_OTP is set.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
