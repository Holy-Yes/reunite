from datetime import timedelta

import numpy as np
import pytest

from app.ml.matching import features as F
from app.ml.matching import zones
from tests.helpers import T0, unit, view


def feat(feats, key):
    return next(f for f in feats if f.key == key)


def test_all_nine_features_in_order():
    feats = F.compute_features(view(kind="lost", category="laptop"), view(kind="found", category="laptop"))
    assert [f.key for f in feats] == F.FEATURES


def test_time_gate_excludes_found_before_lost_window():
    lost = view(kind="lost")
    early = view(kind="found", occurred_from=T0 - timedelta(hours=1), occurred_to=T0 - timedelta(hours=1))
    assert F.compute_features(lost, early) is None
    on_the_dot = view(kind="found", occurred_from=T0, occurred_to=T0)
    assert F.compute_features(lost, on_the_dot) is not None


def test_time_inside_window_is_one_and_decays_after():
    lost = view(kind="lost")  # 09:00 to 13:00
    inside = view(kind="found", occurred_from=T0 + timedelta(hours=2), occurred_to=T0 + timedelta(hours=2))
    assert feat(F.compute_features(lost, inside), "time").value == 1.0
    vals = []
    for h in (1, 6, 24, 72, 200):
        f = view(kind="found", occurred_from=lost.occurred_to + timedelta(hours=h), occurred_to=lost.occurred_to + timedelta(hours=h))
        vals.append(feat(F.compute_features(lost, f), "time").value)
    assert vals == sorted(vals, reverse=True) and vals[0] < 1.0 and vals[-1] > 0.0


def test_zone_decay_is_monotonic_with_hops():
    # Whatever the campus graph is: the further a zone is by walking, the lower the zone score.
    ids = sorted(zones._graph(), key=lambda z: (zones.hops("z_gate", z), z))
    lost = view(kind="lost", zone_id="z_gate")
    vals = [feat(F.compute_features(lost, view(kind="found", zone_id=z)), "zone").value for z in ids]
    hop_counts = [zones.hops("z_gate", z) for z in ids]
    assert vals[0] == 1.0 and vals == sorted(vals, reverse=True)
    assert len(set(hop_counts)) >= 3, "the campus graph should span at least three distances from the gate"
    assert vals[hop_counts.index(max(hop_counts))] < vals[hop_counts.index(min(h for h in hop_counts if h > 0))]


def test_unknown_zone_uses_default_hops():
    assert zones.hops("z_nowhere", "z_gate") == zones.DEFAULT_HOPS


def test_category_credit_levels():
    lost = view(kind="lost", category="earbuds")
    same = feat(F.compute_features(lost, view(kind="found", category="earbuds")), "category").value
    sibling = feat(F.compute_features(lost, view(kind="found", category="headphones")), "category").value
    other = feat(F.compute_features(lost, view(kind="found", category="umbrella")), "category").value
    assert same == 1.0 and sibling == F.SIBLING_CREDIT and other == 0.0
    assert feat(F.compute_features(view(kind="lost"), view(kind="found", category="laptop")), "category").value == F.UNKNOWN_CATEGORY


def test_masks_for_missing_evidence():
    feats = F.compute_features(view(kind="lost"), view(kind="found"))
    for key in ("color", "brand", "image", "text", "cross_modal", "marks"):
        assert feat(feats, key).mask is False
    assert feat(feats, "zone").mask and feat(feats, "time").mask and feat(feats, "category").mask


def test_color_similarity():
    a = view(kind="lost", colors=["black"])
    same = feat(F.compute_features(a, view(kind="found", colors=["black"])), "color")
    close = feat(F.compute_features(a, view(kind="found", colors=["navy"])), "color").value
    far = feat(F.compute_features(a, view(kind="found", colors=["yellow"])), "color").value
    assert same.value == 1.0 and same.detail == "Both black"
    assert close > far


def test_brand():
    a = view(kind="lost", brand="Dell")
    assert feat(F.compute_features(a, view(kind="found", brand="dell")), "brand").value == 1.0
    m = feat(F.compute_features(a, view(kind="found", brand="HP")), "brand")
    assert m.mask and m.value == 0.0


def test_image_text_and_cross_modal_mapping():
    e = unit(1)
    lost = view(kind="lost", image_embs=[e])
    same = feat(F.compute_features(lost, view(kind="found", image_embs=[e])), "image")
    diff = feat(F.compute_features(lost, view(kind="found", image_embs=[unit(2)])), "image")
    assert same.value == 1.0 and diff.value == 0.0
    t = unit(3, 384)
    text = feat(F.compute_features(view(kind="lost", text_emb=t), view(kind="found", text_emb=t)), "text")
    assert text.value == 1.0
    # text on one side, photo on the other: cross-modal is compared, text and image are not
    cross = F.compute_features(view(kind="lost", clip_text_emb=e), view(kind="found", image_embs=[e]))
    assert feat(cross, "cross_modal").mask and not feat(cross, "image").mask and not feat(cross, "text").mask
    assert "You described it; they photographed it" in feat(cross, "cross_modal").detail


def test_marks_jaccard_with_sticker_detail():
    lost = view(kind="lost", marks=["dent", "sticker: crescent moon"])
    exact = feat(F.compute_features(lost, view(kind="found", marks=["dent", "sticker: moon"])), "marks").value
    partial = feat(F.compute_features(lost, view(kind="found", marks=["dent", "scratch"])), "marks").value
    none = feat(F.compute_features(lost, view(kind="found", marks=["cracked"])), "marks").value
    assert exact == 1.0 and 0 < partial < 1 and none == 0.0


# ---- category as a distribution (the classifier's top guesses) --------------------------------

def test_dist_from_attr_normalizes_and_merges_alts():
    d = F.dist_from_attr({"value": "bottle", "confidence": 0.4, "alts": [["watch", 0.2], ["bottle", 0.1]]})
    assert d["bottle"] == pytest.approx(0.5) and d["watch"] == pytest.approx(0.2)
    over = F.dist_from_attr({"value": "a", "confidence": 0.9, "alts": [["b", 0.9]]})
    assert sum(over.values()) == pytest.approx(1.0)
    assert F.dist_from_attr(None) == {} and F.dist_from_attr({"value": ""}) == {}


def test_a_confident_mismatch_scores_zero_and_an_unsure_photo_scores_in_between():
    lost = view(kind="lost", category="laptop", category_conf=0.95)
    confident_bottle = view(kind="found", category="bottle", category_conf=0.95)
    assert feat(F.compute_features(lost, confident_bottle), "category").value < 0.05
    unsure = view(kind="found", category="bottle", category_conf=0.35, category_dist={"bottle": 0.35, "laptop": 0.30, "phone": 0.15})
    mid = feat(F.compute_features(lost, unsure), "category").value
    assert 0.2 < mid < 0.6                                 # it might be a laptop: partial, not zero, not full
    exact = view(kind="found", category="laptop", category_conf=0.95)
    assert feat(F.compute_features(lost, exact), "category").value > 0.9


def test_category_credit_uses_sibling_groups_inside_a_distribution():
    lost = view(kind="lost", category="earbuds", category_conf=0.9)
    found = view(kind="found", category="headphones", category_conf=0.9)
    v = feat(F.compute_features(lost, found), "category").value
    assert 0.4 < v < 0.5                                   # 0.9 * 0.9 * 0.5 plus a little for the leftover probability
