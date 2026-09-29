"""Claim verification: questions from the finder's private details, answer scoring, and the decision rules.

    A = weighted mean of answer scores      (marks 1.5, everything else 1.0 -- serial is asked only as a fallback)
    M = the claimant's own lost-report match score for this item (0 if none)
    S = account signals                      (verified college email; penalty for prior rejections)
    C = 0.60 A + 0.25 M + 0.15 S
"""
from __future__ import annotations

import math
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import taxonomy
from ..config import get_settings
from ..errors import ApiError
from ..ml.matching import zones as zone_graph
from ..ml.text import embedder as text_embedder
from ..models import STAFF_ROLES, Claim, Handover, Item, Match, User
from . import events, handover
from .notify import notify

W_ANSWERS, W_MATCH, W_SIGNALS = 0.60, 0.25, 0.15
REJECT_BELOW, AUTO_AT_LEAST, ASK_MORE_BELOW = 0.45, 0.75, 0.60
MAX_CLAIMS_24H = 3
RETRY_HOURS = 24
FIELD_WEIGHT = {"serial": 1.0, "marks": 1.5}
OPEN = ("draft", "pending_review", "needs_more_info")
LIVE = OPEN + ("approved", "auto_approved")


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


# ---- questions ----------------------------------------------------------------------


def _choices(real: str, pool: list[str], rng: random.Random, n: int = 4) -> list[str]:
    others = [p for p in pool if p.lower() != real.lower()]
    rng.shuffle(others)
    opts = [real, *others[: n - 1]]
    rng.shuffle(opts)
    return opts


def generate_questions(item: Item, seed: str) -> list[dict]:
    """Two or three questions: one easy private detail (weighted higher) if there is one, then place and time.

    Serial number is a fallback, asked only when nothing easier to recall is available -- it's the detail
    people misremember most, so it never displaces a color, brand, or mark question that would score the same.
    """
    rng = random.Random(seed)
    attrs = item.attributes or {}
    non_serial: list[dict] = []

    for m in attrs.get("marks", []):
        head, _, detail = m["value"].partition(":")
        if head == "sticker" and detail.strip():
            non_serial.append({"prompt": "What's on the sticker?", "kind": "text", "field": "marks", "weight": FIELD_WEIGHT["marks"], "expected": detail.strip()})
        else:
            pool = list(taxonomy.marks()) + ["none of these"]
            non_serial.append({"prompt": "Which of these marks does it have?", "kind": "choice", "field": "marks", "weight": FIELD_WEIGHT["marks"], "expected": head, "choices": _choices(head, pool, rng, 4)})
    brand = attrs.get("brand")
    if brand and brand.get("hidden"):
        non_serial.append({"prompt": "Which brand is it?", "kind": "choice", "field": "brand", "weight": 1.0, "expected": brand["value"], "choices": _choices(brand["value"], list(taxonomy.brands()), rng, 4)})
    colors = attrs.get("colors", [])
    if colors and (any(c.get("hidden") for c in colors) or not brand):
        real = colors[0]["value"]
        non_serial.append({"prompt": "What color is it?", "kind": "choice", "field": "colors", "weight": 1.0, "expected": real, "choices": _choices(real, list(taxonomy.palette()), rng, 4)})
    material = attrs.get("material")
    if material:
        non_serial.append({"prompt": "What is it mostly made of?", "kind": "choice", "field": "material", "weight": 1.0, "expected": material["value"], "choices": _choices(material["value"], taxonomy.materials(), rng, 4)})
    non_serial.sort(key=lambda q: -q["weight"])

    serial = attrs.get("serial")
    serial_q = None
    if serial:
        serial_q = {"prompt": "Do you remember any part of the serial number? It's okay if you only remember a little.", "kind": "text", "field": "serial", "weight": FIELD_WEIGHT["serial"], "expected": serial["value"]}

    specific = non_serial[:1] if non_serial else ([serial_q] if serial_q else [])
    picked = [*specific,
              {"prompt": "Where did you last have it?", "kind": "zone", "field": "zone", "weight": 1.0, "expected": item.zone_id},
              {"prompt": "When did you last have it?", "kind": "datetime", "field": "time", "weight": 1.0, "expected": aware(item.occurred_from).isoformat()}]
    return [{"id": f"q{i}", **q} for i, q in enumerate(picked, start=1)]


def public_questions(claim: Claim) -> list[dict]:
    """What the claimant sees: never the expected answer."""
    return [{k: v for k, v in q.items() if k in ("id", "prompt", "kind", "choices")} for q in claim.questions]


# ---- scoring ------------------------------------------------------------------------


def score_answer(q: dict, answer: str) -> float:
    ans, exp = (answer or "").strip(), q["expected"]
    if not ans:
        return 0.0
    kind = q["kind"]
    if kind == "choice":
        return 1.0 if _norm(ans) == _norm(exp) else 0.0
    if kind == "zone":
        h = zone_graph.hops(ans, exp)
        return 1.0 if h == 0 else 0.8 if h == 1 else 0.5 if h == 2 else 0.2
    if kind == "datetime":
        try:
            t = aware(datetime.fromisoformat(ans.replace("Z", "+00:00")))
        except ValueError:
            return 0.0
        ref = aware(datetime.fromisoformat(exp))
        delta_h = (t - ref).total_seconds() / 3600
        if delta_h > 1:  # they claim to have had it after it was found
            return 0.2
        d = abs(delta_h)
        return 1.0 if d <= 3 else math.exp(-(d - 3) / 24)
    if q.get("field") == "serial":
        a, e = re.sub(r"[^A-Z0-9]", "", ans.upper()), re.sub(r"[^A-Z0-9]", "", str(exp).upper())
        if not a or not e:
            return 0.0
        tail = e[-len(a):] if len(a) <= len(e) else e
        return max(fuzz.ratio(a, tail), fuzz.ratio(a, e), fuzz.partial_ratio(a, e)) / 100.0
    fuzzy = fuzz.token_set_ratio(_norm(ans), _norm(str(exp))) / 100.0
    emb = text_embedder.embed_texts([ans, str(exp)])
    cos = float(emb[0] @ emb[1])
    return max(fuzzy, min(1.0, max(0.0, (cos - 0.20) / 0.60)))


def signals_for(db: Session, claimant: User) -> dict:
    now = datetime.now(timezone.utc)
    rejected = db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == claimant.id, Claim.status == "rejected", Claim.updated_at >= now - timedelta(days=30))) or 0
    last24 = db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == claimant.id, Claim.created_at >= now - timedelta(hours=24))) or 0
    pending = db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == claimant.id, Claim.status.in_(OPEN))) or 0
    s = max(0.0, 1.0 - 0.25 * rejected)
    return {"verified_email": True, "claims_24h": last24, "rejected_30d": rejected, "pending_claims": pending, "score": round(s, 3)}


def match_score(db: Session, claimant: User, item: Item) -> float:
    best = db.scalar(
        select(func.max(Match.score)).join(Item, Item.id == Match.lost_item_id).where(Match.found_item_id == item.id, Item.owner_id == claimant.id)
    )
    return float(best or 0.0)


def claim_score(answer_scores: dict, questions: list[dict], m: float, s: float) -> tuple[float, float]:
    """(C, A). Unanswered questions score 0."""
    total_w = sum(q["weight"] for q in questions) or 1.0
    a = sum(q["weight"] * answer_scores.get(q["id"], 0.0) for q in questions) / total_w
    return W_ANSWERS * a + W_MATCH * m + W_SIGNALS * s, a


def decide_status(c: float, item: Item, more_info_asked: bool) -> tuple[str, str | None]:
    """Status for a scored claim, and a note. People always review the categories in ALWAYS_REVIEW."""
    always = (item.category or "") in get_settings().review_categories
    if always:
        return "pending_review", "This kind of item is always checked by a person."
    if c < REJECT_BELOW:
        return "rejected", f"The answers didn't match closely enough. You can try once more after {RETRY_HOURS} hours."
    if c >= AUTO_AT_LEAST and item.value_tier == "low":
        return "auto_approved", None
    if c < ASK_MORE_BELOW and not more_info_asked:
        return "needs_more_info", "One more detail would help."
    return "pending_review", None


# ---- lifecycle ----------------------------------------------------------------------


def _both_events(db: Session, claim: Claim, type_: str, actor: User | None, role: str) -> None:
    events.add_event(db, claim.item_id, type_, actor.id if actor else None, role)
    if claim.match_id and claim.match:
        events.add_event(db, claim.match.lost_item_id, type_, actor.id if actor else None, role)


def _set_claimed(db: Session, claim: Claim) -> None:
    claim.item.status = "claimed"
    if claim.match and claim.match.lost_item.status in ("open", "matched", "processing"):
        claim.match.lost_item.status = "claimed"


def restore_status(db: Session, claim: Claim) -> None:
    """A rejected claim puts the found and lost items back into the pool."""
    live = db.scalar(select(func.count(Claim.id)).where(Claim.item_id == claim.item_id, Claim.id != claim.id, Claim.status.in_(("pending_review", "needs_more_info", "approved", "auto_approved"))))
    if live:
        return
    for it in (claim.item, claim.match.lost_item if claim.match else None):
        if it is not None and it.status == "claimed":
            col = Match.lost_item_id if it.kind == "lost" else Match.found_item_id
            best = db.scalar(select(func.max(Match.score)).where(col == it.id)) or 0.0
            it.status = "matched" if best >= get_settings().band_possible else "open"


def create_claim(db: Session, claimant: User, match_id: uuid.UUID | None, item_id: uuid.UUID | None) -> Claim:
    s = get_settings()
    if s.domains and claimant.email.split("@")[-1].lower() not in s.domains:
        raise ApiError(403, "unverified_email", "Claims need a verified college email.")
    match: Match | None = None
    if match_id:
        match = db.get(Match, match_id)
        if match is None or match.lost_item.owner_id != claimant.id:
            raise ApiError(404, "not_found", "That match isn't here.")
        item = match.found_item
    elif item_id:
        item = db.get(Item, item_id)
    else:
        raise ApiError(422, "invalid_request", "Say which match or item you're claiming.", {"match_id": "required"})
    if item is None or item.kind != "found" or item.status not in ("open", "matched", "claimed"):
        raise ApiError(404, "not_found", "That item isn't available to claim.")
    if item.owner_id == claimant.id:
        raise ApiError(409, "own_item", "You turned this in, so there's nothing to claim.")

    now = datetime.now(timezone.utc)
    if db.scalar(select(func.count(Claim.id)).where(Claim.claimant_id == claimant.id, Claim.created_at >= now - timedelta(hours=24))) >= MAX_CLAIMS_24H:
        raise ApiError(429, "claim_rate_limited", "That's a lot of claims today. Try again tomorrow.", retry_after=3600)
    if db.scalar(select(Claim.id).where(Claim.item_id == item.id, Claim.claimant_id == claimant.id, Claim.status.in_(OPEN))):
        raise ApiError(409, "claim_open", "You already have a claim open on this item.")
    if db.scalar(select(Claim.id).where(Claim.item_id == item.id, Claim.status.in_(("approved", "auto_approved")))):
        raise ApiError(409, "already_claimed", "This item has already been claimed.")
    last_reject = db.scalar(select(Claim.updated_at).where(Claim.item_id == item.id, Claim.claimant_id == claimant.id, Claim.status == "rejected").order_by(Claim.updated_at.desc()).limit(1))
    if last_reject and aware(last_reject) > now - timedelta(hours=RETRY_HOURS):
        raise ApiError(429, "retry_later", "You can try once more after 24 hours.", retry_after=int((aware(last_reject) + timedelta(hours=RETRY_HOURS) - now).total_seconds()))

    claim = Claim(match_id=match.id if match else None, item_id=item.id, claimant_id=claimant.id, status="draft", signals=signals_for(db, claimant))
    if item.category == "id_card":
        serial = ((item.attributes or {}).get("serial") or {}).get("value", "").upper()
        if not claimant.roll_no or claimant.roll_no.upper() != serial:
            raise ApiError(403, "id_card_owner_only", "ID cards go back to the roll number printed on them. Add your roll number in your profile if this is yours.")
        claim.status, claim.verified_by, claim.score, claim.questions = "auto_approved", "roll_number", 1.0, []
        db.add(claim)
        db.flush()
        _approve(db, claim, None)
        db.commit()
        return claim
    claim.questions = generate_questions(item, str(uuid.uuid4()))
    db.add(claim)
    if match:
        match.feedback, match.feedback_at = "mine", now
    db.commit()
    return claim


def _approve(db: Session, claim: Claim, actor: User | None) -> None:
    """Verified: create the handover and tell the claimant."""
    _set_claimed(db, claim)
    handover.issue(db, claim)
    _both_events(db, claim, "claimed", actor, "student")
    _both_events(db, claim, "verified", actor, "desk" if actor and actor.role != "student" else "system")
    collect = claim.item.custody_zone_id or claim.item.zone_id
    notify(db, claim.claimant_id, "handover_ready", "Your handover pass is ready", "Show the QR or the six-digit code when you collect it.", f"/claims/{claim.id}/handover", {"claim_id": str(claim.id), "collect_zone_id": collect})


def submit_answers(db: Session, claim: Claim, answers: list[dict]) -> Claim:
    if claim.status not in ("draft", "needs_more_info"):
        raise ApiError(409, "claim_closed", "This claim can't take more answers.")
    by_id = {q["id"]: q for q in claim.questions}
    given = {a["question_id"]: str(a.get("answer", "")) for a in answers}
    unknown = [k for k in given if k not in by_id]
    if unknown:
        raise ApiError(422, "invalid_request", "Some answers don't match a question.", {"answers": ", ".join(unknown)})
    merged = {**{a["question_id"]: a["answer"] for a in (claim.answers or [])}, **given}
    claim.answers = [{"question_id": k, "answer": v} for k, v in merged.items()]
    scored = {qid: score_answer(by_id[qid], ans) for qid, ans in merged.items() if by_id[qid].get("scored", True)}
    claim.answer_scores = {k: round(v, 3) for k, v in scored.items()}

    claimant = db.get(User, claim.claimant_id)
    assert claimant is not None
    scoring_qs = [q for q in claim.questions if q.get("scored", True)]
    m = match_score(db, claimant, claim.item)
    claim.signals = {**signals_for(db, claimant), "match_score": round(m, 3)}
    c, a = claim_score(scored, scoring_qs, m, claim.signals["score"])
    claim.score = round(c, 4)
    claim.signals["answers_score"] = round(a, 3)

    status, note = decide_status(c, claim.item, claim.more_info_asked)
    if status == "needs_more_info":
        claim.more_info_asked = True
        claim.questions = [*claim.questions, {"id": f"q{len(claim.questions) + 1}", "prompt": "Tell us one more thing only the owner would know.", "kind": "text", "field": "extra", "weight": 1.0, "expected": "", "scored": False}]
    claim.status, claim.decision_note = status, note
    if status == "auto_approved":
        claim.verified_by = "answers"
        _approve(db, claim, None)
    elif status == "pending_review":
        _set_claimed(db, claim)
        _both_events(db, claim, "claimed", None, "student")
        cat = (claim.item.category or "item").replace("_", " ")
        notify(db, claim.item.owner_id, "claim_update", f"Someone says your found {cat} is theirs", "Review their answers next to what you noted.", f"/claims/{claim.id}", {"claim_id": str(claim.id)})
    elif status == "rejected":
        restore_status(db, claim)
        notify(db, claim.claimant_id, "claim_update", "We couldn't verify that claim", note or "", f"/claims/{claim.id}", {"claim_id": str(claim.id)})
    elif status == "needs_more_info":
        notify(db, claim.claimant_id, "claim_update", "One more question about your claim", "Answer one more detail to continue.", f"/claims/{claim.id}", {"claim_id": str(claim.id)})
    db.commit()
    return claim


def decide(db: Session, claim: Claim, actor: User, decision: str, note: str | None) -> Claim:
    if actor.role not in STAFF_ROLES and claim.item.owner_id != actor.id:
        raise ApiError(403, "forbidden", "Only the finder or the desk can decide this.")
    if claim.status not in ("pending_review", "needs_more_info"):
        raise ApiError(409, "claim_closed", "This claim has already been decided.")
    claim.decided_by, claim.decision_note = actor.id, (note or "").strip()[:500] or None
    if decision == "approve":
        claim.status, claim.verified_by = "approved", "reviewer"
        _approve(db, claim, actor)
    elif decision == "reject":
        claim.status = "rejected"
        restore_status(db, claim)
        notify(db, claim.claimant_id, "claim_update", "Your claim wasn't approved", claim.decision_note or f"You can try once more after {RETRY_HOURS} hours.", f"/claims/{claim.id}", {"claim_id": str(claim.id)})
    elif decision == "more_info":
        claim.status, claim.more_info_asked = "needs_more_info", True
        if not any(q.get("field") == "extra" and not claim.answers for q in claim.questions):
            claim.questions = [*claim.questions, {"id": f"q{len(claim.questions) + 1}", "prompt": claim.decision_note or "Tell us one more thing only the owner would know.", "kind": "text", "field": "extra", "weight": 1.0, "expected": "", "scored": False}]
        notify(db, claim.claimant_id, "claim_update", "The finder has one more question", claim.decision_note or "", f"/claims/{claim.id}", {"claim_id": str(claim.id)})
    else:
        raise ApiError(422, "invalid_request", "Decision must be approve, reject or more_info.", {"decision": "invalid"})
    db.commit()
    return claim


def review_rows(claim: Claim) -> list[dict]:
    """For the desk drawer: each answer next to the finder's private detail, with its similarity."""
    answers = {a["question_id"]: a["answer"] for a in (claim.answers or [])}
    return [
        {
            "question_id": q["id"],
            "prompt": q["prompt"],
            "field": q.get("field"),
            "answer": answers.get(q["id"]),
            "expected": q.get("expected"),
            "score": (claim.answer_scores or {}).get(q["id"]),
        }
        for q in claim.questions
    ]
