import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.errors import ApiError
from app.ml.attrs import attr
from app.models import Claim
from app.services import claims as svc
from tests import factories as fx


def found_bottle(db, finder, **kw):
    attrs = {"brand": attr("Milton", 0.95, "text", True), "marks": [attr("sticker: crescent moon", 0.95, "text", True)], "serial": attr("AB12-4F2A", 0.9, "text", True)}
    return fx.item(db, finder, "found", "bottle", attrs=attrs, **kw)


def answers_for(claim, item, correct=True):
    out = []
    for q in claim.questions:
        if not correct:
            out.append({"question_id": q["id"], "answer": "z_sports" if q["kind"] == "zone" else "2020-01-01T00:00:00Z" if q["kind"] == "datetime" else "nothing at all"})
            continue
        exp = q["expected"]
        out.append({"question_id": q["id"], "answer": exp})
    return out


# ---- decision rules ---------------------------------------------------------------

@pytest.mark.parametrize("c,tier,cat,asked,expected", [
    (0.20, "low", "bottle", False, "rejected"),
    (0.44, "low", "bottle", False, "rejected"),
    (0.50, "low", "bottle", False, "needs_more_info"),
    (0.50, "low", "bottle", True, "pending_review"),
    (0.65, "low", "bottle", False, "pending_review"),
    (0.75, "low", "bottle", False, "auto_approved"),
    (0.95, "low", "bottle", False, "auto_approved"),
    (0.95, "high", "tablet", False, "pending_review"),
    (0.95, "high", "laptop", False, "pending_review"),
    (0.95, "low", "phone", False, "pending_review"),
    (0.10, "high", "laptop", False, "pending_review"),  # always review, whatever the score
    (0.95, "low", "id_card", False, "pending_review"),
])
def test_decide_status(db, c, tier, cat, asked, expected):
    owner = fx.user(db, "f@x.edu")
    it = fx.item(db, owner, "found", cat, tier=tier)
    assert svc.decide_status(c, it, asked)[0] == expected


def test_claim_score_formula():
    qs = [{"id": "q1", "weight": 2.0}, {"id": "q2", "weight": 1.0}]
    c, a = svc.claim_score({"q1": 1.0, "q2": 0.0}, qs, m=0.8, s=1.0)
    assert a == pytest.approx(2 / 3)
    assert c == pytest.approx(0.6 * (2 / 3) + 0.25 * 0.8 + 0.15 * 1.0)


# ---- questions -------------------------------------------------------------------

def test_questions_prefer_easier_attributes_over_serial(db):
    finder = fx.user(db, "f@x.edu")
    it = found_bottle(db, finder)
    qs = svc.generate_questions(it, "seed")
    assert 2 <= len(qs) <= 3
    assert qs[0]["field"] != "serial"
    assert qs[0]["prompt"] == "What's on the sticker?"
    assert {q["kind"] for q in qs} >= {"zone", "datetime"}


def test_questions_fall_back_to_serial_when_nothing_easier(db):
    finder = fx.user(db, "f@x.edu")
    it = fx.item(db, finder, "found", "bottle", attrs={"colors": [], "serial": attr("AB12-4F2A", 0.9, "text", True)})
    qs = svc.generate_questions(it, "seed")
    assert qs[0]["field"] == "serial"
    assert qs[0]["prompt"].startswith("Do you remember any part of the serial number")


def test_public_questions_never_leak_expected_answers(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = found_bottle(db, finder)
    lost = fx.item(db, claimant, "lost", "bottle")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it).id, None)
    for q in svc.public_questions(claim):
        assert set(q) <= {"id", "prompt", "kind", "choices"}
    blob = str(svc.public_questions(claim))
    assert "crescent" not in blob and "4F2A" not in blob


def test_choice_questions_include_the_real_answer_and_distractors(db):
    finder = fx.user(db, "f@x.edu")
    it = fx.item(db, finder, "found", "bottle", attrs={"brand": attr("Milton", 0.95, "text", True)})
    q = next(q for q in svc.generate_questions(it, "s") if q["field"] == "brand")
    assert q["expected"] in q["choices"] and len(set(q["choices"])) == 4


# ---- answer scoring ----------------------------------------------------------------

def test_answer_scoring():
    text = {"kind": "text", "expected": "crescent moon", "field": "marks"}
    assert svc.score_answer(text, "Crescent moon") == 1.0
    assert svc.score_answer(text, "moon crescent") > 0.9
    assert svc.score_answer(text, "a red rose") < 0.6
    assert svc.score_answer(text, "") == 0.0
    serial = {"kind": "text", "expected": "AB12-4F2A", "field": "serial"}
    assert svc.score_answer(serial, "4f2a") == 1.0
    assert svc.score_answer(serial, "9999") < 0.5
    choice = {"kind": "choice", "expected": "Milton", "field": "brand"}
    assert svc.score_answer(choice, "milton") == 1.0 and svc.score_answer(choice, "Cello") == 0.0


def test_zone_and_datetime_scoring():
    z = {"kind": "zone", "expected": "z_library"}
    assert svc.score_answer(z, "z_library") == 1.0
    assert svc.score_answer(z, "z_canteen") == 0.8  # one hop
    assert svc.score_answer(z, "z_hostel3") <= 0.5
    ref = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
    d = {"kind": "datetime", "expected": ref.isoformat()}
    assert svc.score_answer(d, (ref - timedelta(hours=2)).isoformat()) == 1.0
    assert 0 < svc.score_answer(d, (ref - timedelta(hours=30)).isoformat()) < 0.5
    assert svc.score_answer(d, (ref + timedelta(hours=5)).isoformat()) == 0.2  # "had it" after it was found
    assert svc.score_answer(d, "not a date") == 0.0


# ---- lifecycle and hard blocks -----------------------------------------------------

def test_good_answers_auto_approve_a_low_value_item(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = found_bottle(db, finder)
    lost = fx.item(db, claimant, "lost", "bottle")
    m = fx.match(db, lost, it, 0.85)
    claim = svc.create_claim(db, claimant, m.id, None)
    assert claim.status == "draft"
    claim = svc.submit_answers(db, claim, answers_for(claim, it))
    assert claim.status == "auto_approved" and claim.verified_by == "answers" and claim.score >= 0.75
    assert it.status == "claimed" and lost.status == "claimed"
    from app.models import Handover
    assert db.query(Handover).filter_by(claim_id=claim.id).one()


def test_wrong_answers_are_rejected_and_items_go_back_to_the_pool(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = found_bottle(db, finder)
    lost = fx.item(db, claimant, "lost", "bottle")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it, 0.2).id, None)
    claim = svc.submit_answers(db, claim, answers_for(claim, it, correct=False))
    assert claim.status == "rejected" and "24 hours" in claim.decision_note
    assert it.status in ("open", "matched")
    with pytest.raises(ApiError) as e:  # can try once more after 24 hours, not now
        svc.create_claim(db, claimant, None, it.id)
    assert e.value.status == 429 and e.value.retry_after


def test_laptop_goes_to_a_person_even_with_perfect_answers(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = fx.item(db, finder, "found", "laptop", attrs={"serial": attr("ZX99-1234", 0.9, "text", True)})
    lost = fx.item(db, claimant, "lost", "laptop")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it, 0.9).id, None)
    claim = svc.submit_answers(db, claim, answers_for(claim, it))
    assert claim.status == "pending_review" and "person" in claim.decision_note
    assert claim.item.owner_id == finder.id


def test_middling_answers_ask_for_more_once(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = found_bottle(db, finder)
    lost = fx.item(db, claimant, "lost", "bottle")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it, 0.55).id, None)
    good = answers_for(claim, it)
    half = [a if i < 1 else {**a, "answer": "wrong"} for i, a in enumerate(good)]
    claim = svc.submit_answers(db, claim, half)
    assert claim.status == "needs_more_info" and claim.more_info_asked
    assert claim.questions[-1]["field"] == "extra"
    claim = svc.submit_answers(db, claim, [{"question_id": claim.questions[-1]["id"], "answer": "It has my name inside the lid"}])
    assert claim.status in ("pending_review", "auto_approved", "rejected")
    assert claim.status != "needs_more_info"


def test_hard_blocks(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = found_bottle(db, finder)
    lost = fx.item(db, claimant, "lost", "bottle")
    m = fx.match(db, lost, it)
    svc.create_claim(db, claimant, m.id, None)
    with pytest.raises(ApiError) as e:   # second open claim on the same item
        svc.create_claim(db, claimant, m.id, None)
    assert e.value.status == 409
    with pytest.raises(ApiError) as e:   # your own item
        svc.create_claim(db, finder, None, it.id)
    assert e.value.code == "own_item"
    others = [found_bottle(db, finder) for _ in range(3)]
    for o in others[:2]:
        svc.create_claim(db, claimant, None, o.id)
    with pytest.raises(ApiError) as e:   # more than 3 claims in 24 hours
        svc.create_claim(db, claimant, None, others[2].id)
    assert e.value.status == 429 and e.value.code == "claim_rate_limited"


def test_unverified_email_domain_blocks_claims(db, monkeypatch):
    from app.config import get_settings
    finder, claimant = fx.user(db, "f@college.edu"), fx.user(db, "c@gmail.com")
    it = found_bottle(db, finder)
    monkeypatch.setattr(get_settings(), "allowed_email_domains", "college.edu")
    with pytest.raises(ApiError) as e:
        svc.create_claim(db, claimant, None, it.id)
    assert e.value.code == "unverified_email"


def test_id_card_claim_uses_roll_number_and_skips_questions(db):
    finder = fx.user(db, "f@x.edu")
    owner = fx.user(db, "o@x.edu", roll_no="21071A0542")
    stranger = fx.user(db, "s@x.edu", roll_no="21071A0599")
    card = fx.item(db, finder, "found", "id_card", attrs={"serial": attr("21071A0542", 0.95, "ocr")}, tier="low")
    with pytest.raises(ApiError) as e:
        svc.create_claim(db, stranger, None, card.id)
    assert e.value.code == "id_card_owner_only"
    claim = svc.create_claim(db, owner, None, card.id)
    assert claim.status == "auto_approved" and claim.verified_by == "roll_number" and claim.questions == []


# ---- desk and finder decisions --------------------------------------------------------

def test_finder_and_desk_decisions(db):
    finder, claimant, desk, other = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu"), fx.user(db, "d@x.edu", "desk"), fx.user(db, "o@x.edu")
    it = fx.item(db, finder, "found", "laptop", attrs={"serial": attr("ZX99-1234", 0.9, "text", True)})
    lost = fx.item(db, claimant, "lost", "laptop")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it, 0.9).id, None)
    claim = svc.submit_answers(db, claim, answers_for(claim, it))
    with pytest.raises(ApiError) as e:
        svc.decide(db, claim, other, "approve", None)
    assert e.value.status == 403
    claim = svc.decide(db, claim, desk, "more_info", "Which sticker is on the lid?")
    assert claim.status == "needs_more_info"
    claim = svc.submit_answers(db, claim, [{"question_id": claim.questions[-1]["id"], "answer": "crescent moon"}])
    assert claim.status == "pending_review"
    claim = svc.decide(db, claim, finder, "approve", "looks right")
    assert claim.status == "approved" and claim.verified_by == "reviewer"
    with pytest.raises(ApiError):
        svc.decide(db, claim, finder, "reject", None)   # already decided


def test_rejection_by_finder_restores_status(db):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = fx.item(db, finder, "found", "laptop", attrs={"serial": attr("ZX99-1234", 0.9, "text", True)})
    lost = fx.item(db, claimant, "lost", "laptop")
    claim = svc.create_claim(db, claimant, fx.match(db, lost, it, 0.9).id, None)
    claim = svc.submit_answers(db, claim, answers_for(claim, it))
    assert it.status == "claimed"
    svc.decide(db, claim, finder, "reject", "serial doesn't match")
    assert claim.status == "rejected" and it.status == "matched" and lost.status == "matched"
