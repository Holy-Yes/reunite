from datetime import datetime, timedelta, timezone

import pytest

from app.errors import ApiError
from app.ml.attrs import attr
from app.models import Handover
from app.security import make_handover_token
from app.services import claims as claims_svc, handover as ho
from tests import factories as fx


def setup(db, category="bottle"):
    finder, claimant, desk = fx.user(db, "f@x.edu"), fx.user(db, "c@x.edu"), fx.user(db, "d@x.edu", "desk")
    attrs = {"serial": attr("AB12-4F2A", 0.9, "text", True)} if category != "id_card" else {"serial": attr("21071A0542", 0.9, "ocr")}
    it = fx.item(db, finder, "found", category, attrs=attrs, tier="low")
    lost = fx.item(db, claimant, "lost", category)
    m = fx.match(db, lost, it, 0.9)
    if category == "id_card":
        claimant.roll_no = "21071A0542"
        db.commit()
        claim = claims_svc.create_claim(db, claimant, None, it.id)
    else:
        claim = claims_svc.create_claim(db, claimant, m.id, None)
        claim = claims_svc.submit_answers(db, claim, [{"question_id": q["id"], "answer": q["expected"]} for q in claim.questions])
    assert claim.status == "auto_approved"
    h = db.query(Handover).filter_by(claim_id=claim.id).one()
    return finder, claimant, desk, it, lost, claim, h


def test_confirm_with_code_completes_the_return(db):
    finder, claimant, desk, it, lost, claim, h = setup(db)
    code = ho.payload(claim, h)["code"]
    assert len(code) == 6 and code.isdigit()
    claim2, item2 = ho.confirm(db, desk, code, None, False)
    assert claim2.status == "handed_over" and it.status == "returned" and lost.status == "returned"
    assert finder.points == 10
    from app.services import events
    assert [e["type"] for e in events.timeline(db, lost.id)][-1] == "handed_over"
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, code, None, False)
    assert e.value.status in (400, 409)


def test_confirm_with_token(db):
    _, claimant, desk, it, lost, claim, h = setup(db)
    token = ho.payload(claim, h)["qr_payload"]
    ho.confirm(db, desk, None, token, False)
    assert it.status == "returned"


def test_finder_can_confirm_but_a_stranger_cannot(db):
    finder, claimant, desk, it, lost, claim, h = setup(db)
    stranger = fx.user(db, "s@x.edu")
    code = ho.payload(claim, h)["code"]
    with pytest.raises(ApiError) as e:
        ho.confirm(db, stranger, code, None, False)
    assert e.value.status == 403
    ho.confirm(db, finder, code, None, False)


def test_wrong_code_and_attempt_limit(db):
    _, _, desk, it, lost, claim, h = setup(db)
    for i in range(5):
        with pytest.raises(ApiError) as e:
            ho.confirm(db, desk, "000000" if i % 2 == 0 else "111111", None, False)
        assert e.value.code == "invalid_code"
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, ho.payload(claim, h)["code"], None, False)  # even the right code is refused now
    assert e.value.status == 429 and e.value.retry_after
    assert it.status == "claimed"


def test_expired_code_and_reissue(db):
    _, claimant, desk, it, lost, claim, h = setup(db)
    old = ho.payload(claim, h)["code"]
    h.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert ho.payload(claim, h)["expired"] is True
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, old, None, False)
    assert e.value.status == 410 and e.value.code == "handover_expired"
    fresh = ho.issue(db, claim)
    new = ho.payload(claim, fresh)
    assert new["code"] != old and new["expired"] is False
    with pytest.raises(ApiError):
        ho.confirm(db, desk, old, None, False)   # the old code no longer works
    ho.confirm(db, desk, new["code"], None, False)


def test_tampered_and_expired_tokens(db):
    _, _, desk, it, lost, claim, h = setup(db)
    token = ho.payload(claim, h)["qr_payload"]
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, None, token[:-3] + "abc", False)
    assert e.value.code == "invalid_code"
    expired = make_handover_token(claim.id, h.token_jti, datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, None, expired, False)
    assert e.value.status == 410
    stale = make_handover_token(claim.id, "old-jti", datetime.now(timezone.utc) + timedelta(minutes=5))
    with pytest.raises(ApiError):
        ho.confirm(db, desk, None, stale, False)


def test_id_card_needs_the_desk_to_check_the_id(db):
    _, claimant, desk, it, lost, claim, h = setup(db, "id_card")
    code = ho.payload(claim, h)["code"]
    with pytest.raises(ApiError) as e:
        ho.confirm(db, desk, code, None, False)
    assert e.value.code == "id_check_required"
    ho.confirm(db, desk, code, None, True)
    assert db.get(Handover, h.id).id_checked is True
