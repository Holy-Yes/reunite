"""Item lifecycle: create, edit, close, and the ingest and extract job bodies."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import get_settings
from ..errors import ApiError
from ..ml import pipeline
from ..ml.attrs import attr
from ..ml.embed_util import to_bytes
from ..models import STAFF_ROLES, AttributeLabel, Item, ItemImage, User, Zone
from . import events, media
from . import zones as zones_svc
from .notify import notify

HIGH_VALUE = {"laptop", "phone", "tablet", "watch", "earbuds", "headphones"}
DEFAULT_HIDDEN_FIELDS = ("marks", "serial")  # suggested private on found reports: they verify the owner
EDITABLE = ("processing", "open", "matched")


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_ticket(db: Session, kind: str) -> str:
    prefix = "RU-L-" if kind == "lost" else "RU-F-"
    rows = db.scalars(select(Item.ticket_no).where(Item.ticket_no.like(prefix + "%")))
    top = max((int(t[len(prefix):]) for t in rows if t[len(prefix):].isdigit()), default=0)
    return f"{prefix}{top + 1:04d}"


def clean_attributes(raw: str | dict | None) -> dict:
    """Validate the attributes JSON a client sends (chips it edited). Unknown fields and bad shapes are dropped."""
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ApiError(422, "invalid_request", "Attributes must be valid JSON.", {"attributes": "invalid JSON"}) from e
    if not isinstance(raw, dict):
        raise ApiError(422, "invalid_request", "Attributes must be an object.", {"attributes": "expected object"})

    def one(a: object) -> dict | None:
        if not isinstance(a, dict) or not isinstance(a.get("value"), str) or not a["value"].strip():
            return None
        src = a.get("source") if a.get("source") in ("photo", "text", "ocr", "user") else "user"
        try:
            conf = min(1.0, max(0.0, float(a.get("confidence", 1.0))))
        except (TypeError, ValueError):
            conf = 1.0
        return attr(a["value"].strip()[:120], conf, src, bool(a.get("hidden")))

    out: dict = {}
    for f in ("category", "brand", "material", "serial"):
        if f in raw:
            out[f] = one(raw[f])
    if out.get("category") and out["category"]["value"] not in taxonomy.category_names():
        raise ApiError(422, "invalid_request", "That category isn't one we know.", {"attributes.category": "unknown category"})
    for f in ("colors", "marks"):
        if f in raw and isinstance(raw[f], list):
            out[f] = [a for a in (one(x) for x in raw[f]) if a]
    return {k: v for k, v in out.items() if v is not None or k in ("category", "brand", "material", "serial")}


def _check_zone(db: Session, zone_id: str | None, field: str) -> None:
    if zone_id and db.get(Zone, zone_id) is None:
        raise ApiError(422, "invalid_request", "That place isn't on the campus map.", {field: "unknown zone"})


def create_item(
    db: Session,
    user: User,
    *,
    kind: str,
    text: str,
    zone_id: str,
    occurred_from: datetime,
    occurred_to: datetime,
    custody_zone_id: str | None,
    attributes: str | dict | None,
    photos: list[bytes],
    lat: float | None = None,
    lon: float | None = None,
) -> Item:
    if kind not in ("lost", "found"):
        raise ApiError(422, "invalid_request", "Kind must be lost or found.", {"kind": "lost or found"})
    text = (text or "").strip()
    if not text and not photos:
        raise ApiError(422, "invalid_request", "Describe it or add a photo.", {"text": "add a description or a photo"})
    if len(photos) > 3:
        raise ApiError(422, "invalid_request", "Up to three photos.", {"photos": "too many"})
    if aware(occurred_to) < aware(occurred_from):
        raise ApiError(422, "invalid_request", "The end time is before the start time.", {"occurred_to": "before occurred_from"})
    if (lat is None) != (lon is None) or (lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180)):
        raise ApiError(422, "invalid_request", "That map position isn't valid.", {"lat": "invalid"})
    if lat is not None and not zone_id:
        zone_id = zones_svc.nearest_zone(db, lat, lon) or ""  # a pin alone is enough: the list place follows from it
    _check_zone(db, zone_id, "zone_id")
    _check_zone(db, custody_zone_id, "custody_zone_id")
    if kind == "lost":
        custody_zone_id = None

    item = Item(
        ticket_no=next_ticket(db, kind), kind=kind, status="processing", owner_id=user.id, description=text,
        attributes=clean_attributes(attributes), hidden_attributes={}, zone_id=zone_id, lat=lat, lon=lon,
        occurred_from=aware(occurred_from), occurred_to=aware(occurred_to), custody_zone_id=custody_zone_id,
    )
    db.add(item)
    db.flush()
    for data in photos:
        path, sha = media.stash_incoming(data)
        db.add(ItemImage(item_id=item.id, path=path, sha256=sha))
    events.add_event(db, item.id, "reported", user.id, "student" if kind == "lost" else "finder")
    db.flush()
    return item


# ---- job bodies ---------------------------------------------------------------------


def run_ingest(db: Session, item_id: uuid.UUID) -> None:
    item = db.get(Item, item_id)
    if item is None:
        return
    redact = ((item.attributes or {}).get("category") or {}).get("value") == "id_card"
    for row in item.images:
        if row.path.startswith("incoming/") or not row.public_path:
            media.process_image(row, redact)
    db.commit()


def run_extract(db: Session, item_id: uuid.UUID) -> dict | None:
    """Photos and text to attributes and embeddings; the item becomes open. Returns the extraction summary."""
    item = db.get(Item, item_id)
    if item is None:
        return None
    previous_status = item.status
    images = [media.load_original(r) for r in item.images if not r.path.startswith("incoming/")]
    ex = pipeline.extract(item.description, images)

    provided = item.attributes or {}
    attributes = pipeline.merge_user_attributes(ex.attributes, provided)
    if item.kind == "found":  # suggest privacy for the details that verify an owner, unless the finder decided
        for f in DEFAULT_HIDDEN_FIELDS:
            val = attributes.get(f)
            was_provided = f in provided and provided[f]
            if not val or was_provided:
                continue
            for a in (val if isinstance(val, list) else [val]):
                if a.get("source") != "user":
                    a["hidden"] = True
    item.attributes = attributes
    item.hidden_attributes = pipeline.split_hidden(attributes)
    cat = (attributes.get("category") or {}).get("value")
    item.category = cat
    item.category_group = taxonomy.category_group(cat)
    item.value_tier = "high" if cat in HIGH_VALUE else "low"
    item.text_embedding = to_bytes(ex.text_embedding)
    item.clip_text_embedding = to_bytes(ex.clip_text_embedding)
    redact = cat == "id_card"
    item.redacted = redact

    live = [r for r in item.images if not r.path.startswith("incoming/")]
    for row, res in zip(live, ex.images):
        row.detections = res.detections
        row.primary_crop = res.primary_crop
        row.ocr_text = res.ocr_text
        row.embedding = to_bytes(res.embedding)
        media.write_public(row, images[live.index(row)], redact)  # redaction may have changed with the category

    if previous_status == "processing":
        item.status = "open"
    db.commit()

    roll = next((r.roll_no for r in ex.images if r.roll_no), None) or _roll_from(attributes)
    if item.kind == "found" and cat == "id_card" and roll:
        _notify_id_owner(db, item, roll)
    return {"category": cat, "roll_no": roll}


def _roll_from(attributes: dict) -> str | None:
    serial = (attributes.get("serial") or {}).get("value", "")
    m = re.fullmatch(get_settings().roll_no_regex, serial.upper())
    return m.group(0) if m else None


def _notify_id_owner(db: Session, item: Item, roll: str) -> None:
    """ID cards carry the owner's roll number: tell that user directly, and only once."""
    owner = db.scalar(select(User).where(User.roll_no == roll.upper()))
    if owner is None or owner.id == item.owner_id:
        return
    from ..models import Notification

    if db.scalar(select(Notification.id).where(Notification.user_id == owner.id, Notification.type == "claim_update", Notification.data["item_id"].as_string() == str(item.id))):
        return
    notify(
        db, owner.id, "claim_update", "Your ID card was turned in",
        "Someone handed in a card with your roll number. Confirm it's yours and collect it from the desk.",
        f"/claims/new?item={item.id}", {"item_id": str(item.id)},
    )
    db.commit()


# ---- edit / close ---------------------------------------------------------------------


def apply_edit(db: Session, item: Item, actor: User, body: dict) -> tuple[bool, bool]:
    """Apply an owner's PATCH. Returns (text_or_photos_changed, anything_changed)."""
    if item.status not in EDITABLE:
        raise ApiError(409, "not_editable", "This report can't be changed any more.")
    changed = text_changed = False
    attrs = dict(item.attributes or {})

    def label(field: str, old: object, new: object) -> None:
        db.add(AttributeLabel(item_id=item.id, field=field, old_value=old, new_value=new, source="user"))

    if "text" in body and body["text"] is not None and body["text"].strip() != item.description:
        item.description = body["text"].strip()
        changed = text_changed = True
    if "attributes" in body and body["attributes"] is not None:
        new = clean_attributes(body["attributes"])
        for f, v in new.items():
            old = attrs.get(f)
            if old != v:
                label(f, old, v)
                if v is None:
                    attrs.pop(f, None)
                else:
                    attrs[f] = v if isinstance(v, list) else {**v, "source": "user", "confidence": 1.0}
                changed = True
        item.attributes = attrs
    if "hidden" in body and isinstance(body["hidden"], dict):  # {"marks": true, "serial": false}
        for f, flag in body["hidden"].items():
            val = attrs.get(f)
            for a in (val if isinstance(val, list) else [val] if val else []):
                if bool(a.get("hidden")) != bool(flag):
                    a["hidden"] = bool(flag) or None
                    if not a["hidden"]:
                        a.pop("hidden")
                    changed = True
        item.attributes = attrs
    for f in ("zone_id", "custody_zone_id"):
        if f in body and body[f] and body[f] != getattr(item, f):
            _check_zone(db, body[f], f)
            setattr(item, f, body[f])
            changed = True
    for f in ("occurred_from", "occurred_to"):
        if body.get(f):
            setattr(item, f, aware(body[f]))
            changed = True
    if aware(item.occurred_to) < aware(item.occurred_from):
        raise ApiError(422, "invalid_request", "The end time is before the start time.", {"occurred_to": "before occurred_from"})
    if changed:
        item.hidden_attributes = pipeline.split_hidden(item.attributes)
        cat = (item.attributes.get("category") or {}).get("value")
        item.category, item.category_group = cat, taxonomy.category_group(cat)
        item.status = "processing"
    return text_changed, changed


def close_item(db: Session, item: Item, actor: User, reason: str | None) -> Item:
    if item.status in ("closed", "returned"):
        raise ApiError(409, "already_closed", "This report is already closed.")
    if item.status == "claimed" and actor.role not in STAFF_ROLES:
        raise ApiError(409, "claim_open", "There's an open claim on this. Ask the desk to close it.")
    item.status = "closed"
    item.closed_at = datetime.now(timezone.utc)
    events.add_event(db, item.id, "closed", actor.id, "desk" if actor.role != "student" else ("student" if item.kind == "lost" else "finder"), {"note": (reason or "")[:200]})
    db.commit()
    return item
