"""security_guard is a handover-only role: it can complete someone else's handover, but gets none of the
desk role's other powers (claims queue, item-close override, masked chat)."""
import pytest

from app.errors import ApiError
from app.ml.attrs import attr
from app.models import Handover
from app.services import chat as chat_svc, claims as claims_svc, handover as ho, items as items_svc
from tests import factories as fx


def _approved_claim(db, category="bottle"):
    finder, claimant = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu")
    it = fx.item(db, finder, "found", category, attrs={"serial": attr("AB12-4F2A", 0.9, "text", True)}, tier="low")
    lost = fx.item(db, claimant, "lost", category)
    m = fx.match(db, lost, it, 0.9)
    claim = claims_svc.create_claim(db, claimant, m.id, None)
    claim = claims_svc.submit_answers(db, claim, [{"question_id": q["id"], "answer": q["expected"]} for q in claim.questions])
    return finder, claimant, it, lost, claim


def test_guard_can_confirm_someone_elses_handover(db):
    finder, claimant, it, lost, claim = _approved_claim(db)
    assert claim.status == "auto_approved"
    guard = fx.user(db, "g@x.edu", "security_guard")
    h = db.query(Handover).filter_by(claim_id=claim.id).one()
    code = ho.payload(claim, h)["code"]
    claim2, item2 = ho.confirm(db, guard, code, None, False)
    assert claim2.status == "handed_over" and item2.status == "returned"


def test_guard_cannot_decide_someone_elses_claim(db):
    finder, claimant, it, lost, claim = _approved_claim(db, "laptop")
    guard = fx.user(db, "g@x.edu", "security_guard")
    with pytest.raises(ApiError) as e:
        claims_svc.decide(db, claim, guard, "approve", "looks fine")
    assert e.value.status == 403


def test_guard_cannot_override_close_on_a_claimed_item(db):
    finder, claimant, it, lost, claim = _approved_claim(db)
    it.status = "claimed"
    guard = fx.user(db, "g@x.edu", "security_guard")
    with pytest.raises(ApiError) as e:
        items_svc.close_item(db, it, guard, "no reason")
    assert e.value.code == "claim_open"


def test_guard_is_not_a_chat_participant(db):
    finder, claimant, it, lost, claim = _approved_claim(db)
    guard = fx.user(db, "g@x.edu", "security_guard")
    with pytest.raises(ApiError) as e:
        chat_svc.thread(db, claim, guard)
    assert e.value.status == 404
