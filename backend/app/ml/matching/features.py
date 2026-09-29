"""Per-pair features. Each is a value in [0, 1] plus a mask (False = not comparable, and left out of
the score). Time is also a hard gate: a found moment before the lost window starts is excluded."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ... import taxonomy
from ..vision import color
from . import zones

FEATURES = ["category", "color", "brand", "image", "text", "cross_modal", "marks", "zone", "time"]
LABELS = {
    "category": "Type",
    "color": "Color",
    "brand": "Brand",
    "image": "Photo",
    "text": "Words",
    "cross_modal": "Words vs photo",
    "marks": "Marks",
    "zone": "Place",
    "time": "Time",
}

# Mapping constants: starting values, refit by calibrate.py.
IMAGE_LO, IMAGE_HI = 0.55, 0.90
TEXT_LO, TEXT_HI = 0.20, 0.80
CROSS_LO, CROSS_HI = 0.15, 0.35
COLOR_DE_SCALE = 12.0
ZONE_HOP_SCALE = 6.0
TIME_DECAY_HOURS = 72.0
SIBLING_CREDIT = 0.5
UNKNOWN_CATEGORY = 0.3


@dataclass
class ItemView:
    """Everything the matcher needs about one item. Built from a DB row, or straight from a manifest by the eval harness."""

    id: str
    kind: str  # lost | found
    zone_id: str
    occurred_from: datetime
    occurred_to: datetime
    category: str | None = None
    category_conf: float = 1.0
    category_dist: dict[str, float] = field(default_factory=dict)  # top guesses with probabilities; see dist_from_attr
    colors: list[str] = field(default_factory=list)
    brand: str | None = None
    marks: list[str] = field(default_factory=list)
    image_embs: list[np.ndarray] = field(default_factory=list)
    text_emb: np.ndarray | None = None
    clip_text_emb: np.ndarray | None = None

    @property
    def dist(self) -> dict[str, float]:
        """The category as a distribution over categories (the classifier's top guesses), for gating and scoring."""
        if self.category_dist:
            return self.category_dist
        return {self.category: self.category_conf} if self.category else {}

    @property
    def group(self) -> str | None:
        return taxonomy.category_group(self.category)

    @property
    def has_photo(self) -> bool:
        return bool(self.image_embs)

    @property
    def has_text(self) -> bool:
        return self.text_emb is not None


@dataclass
class Feature:
    key: str
    value: float
    mask: bool  # True = compared
    detail: str
    note: str = ""  # why it was not compared

    @property
    def label(self) -> str:
        return LABELS[self.key]


def dist_from_attr(cat: dict | None) -> dict[str, float]:
    """A category attribute {value, confidence, alts?: [[category, prob], ...]} as {category: probability}, summing to at most 1."""
    if not cat or not cat.get("value"):
        return {}
    p = {cat["value"]: float(cat.get("confidence", 1.0))}
    for c, q in cat.get("alts", []) or []:
        p[c] = p.get(c, 0.0) + float(q)
    total = sum(p.values())
    return {k: v / total for k, v in p.items()} if total > 1.0 else p


def _credit(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ga, gb = taxonomy.category_group(a), taxonomy.category_group(b)
    return SIBLING_CREDIT if ga and ga == gb else 0.0


def clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _nice(name: str | None) -> str:
    return (name or "").replace("_", " ")


# ---- individual features ----------------------------------------------------------


def f_category(lost: ItemView, found: ItemView) -> Feature:
    """Expected credit over both sides' category distributions: 1.0 for the same category, sibling credit for the
    same group, 0 otherwise, and UNKNOWN_CATEGORY for whatever probability mass the classifier left unassigned.
    A confident mismatch scores about 0; an unsure photo scores in between."""
    pa, pb = lost.dist, found.dist
    a, b = lost.category, found.category
    if not pa or not pb:
        return Feature("category", UNKNOWN_CATEGORY, True, "The type isn't clear on one side")
    ma, mb = sum(pa.values()), sum(pb.values())
    v = sum(x * y * _credit(i, j) for i, x in pa.items() for j, y in pb.items())
    v += UNKNOWN_CATEGORY * ((1 - ma) * mb + (1 - mb) * ma + (1 - ma) * (1 - mb))
    v = clip01(v)
    if a == b:
        return Feature("category", v, True, f"Both are {_nice(a)}s" if not a.endswith("s") else f"Both are {_nice(a)}")
    if lost.group and lost.group == found.group:
        return Feature("category", v, True, f"{_nice(a).capitalize()} and {_nice(b)} are close")
    return Feature("category", v, True, f"{_nice(a).capitalize()} vs {_nice(b)}")


def f_color(lost: ItemView, found: ItemView) -> Feature:
    if not lost.colors or not found.colors:
        return Feature("color", 0.0, False, "", "no color")
    short, long_ = sorted([lost.colors, found.colors], key=len)
    best = 0.0
    for perm in itertools.permutations(long_, len(short)):
        sims = [math.exp(-color.palette_delta_e(s, p) / COLOR_DE_SCALE) for s, p in zip(short, perm)]
        best = max(best, sum(sims) / len(sims))
    if set(lost.colors) == set(found.colors):
        detail = "Both " + " and ".join(lost.colors)
    else:
        detail = f"{' and '.join(lost.colors).capitalize()} vs {' and '.join(found.colors)}"
    return Feature("color", clip01(best), True, detail)


def f_brand(lost: ItemView, found: ItemView) -> Feature:
    if not lost.brand or not found.brand:
        return Feature("brand", 0.0, False, "", "no brand")
    if lost.brand.lower() == found.brand.lower():
        return Feature("brand", 1.0, True, f"Both {lost.brand}")
    return Feature("brand", 0.0, True, f"{lost.brand} vs {found.brand}")


def f_image(lost: ItemView, found: ItemView) -> Feature:
    if not lost.image_embs or not found.image_embs:
        return Feature("image", 0.0, False, "", "no photo")
    c = max(_cos(a, b) for a in lost.image_embs for b in found.image_embs)
    v = clip01((c - IMAGE_LO) / (IMAGE_HI - IMAGE_LO))
    detail = "Very similar photos" if v >= 0.85 else "Similar shape and finish" if v >= 0.4 else "The photos look different"
    return Feature("image", v, True, detail)


def f_text(lost: ItemView, found: ItemView) -> Feature:
    if lost.text_emb is None or found.text_emb is None:
        return Feature("text", 0.0, False, "", "no description")
    c = _cos(lost.text_emb, found.text_emb)
    v = clip01((c - TEXT_LO) / (TEXT_HI - TEXT_LO))
    detail = "The descriptions say the same thing" if v >= 0.85 else "Descriptions overlap" if v >= 0.4 else "The descriptions differ"
    return Feature("text", v, True, detail)


def f_cross_modal(lost: ItemView, found: ItemView) -> Feature:
    pairs = []
    if lost.clip_text_emb is not None and found.image_embs:
        pairs.append(("lost_text", max(_cos(lost.clip_text_emb, e) for e in found.image_embs)))
    if found.clip_text_emb is not None and lost.image_embs:
        pairs.append(("found_text", max(_cos(found.clip_text_emb, e) for e in lost.image_embs)))
    if not pairs:
        return Feature("cross_modal", 0.0, False, "", "no text-photo pairing")
    _, c = max(pairs, key=lambda p: p[1])
    v = clip01((c - CROSS_LO) / (CROSS_HI - CROSS_LO))
    only_one_side_has_photo = not (lost.has_photo and found.has_photo)
    detail = "You described it; they photographed it. We compared your words to their photo." if only_one_side_has_photo else "Words compared with the photo"
    return Feature("cross_modal", v, True, detail if v >= 0.4 else "Words don't fit the photo well")


def _mark_sets(marks: list[str]) -> tuple[set[str], dict[str, set[str]]]:
    base: set[str] = set()
    detail: dict[str, set[str]] = {}
    for m in marks:
        head, _, tail = m.partition(":")
        head = head.strip().lower()
        base.add(head)
        if tail.strip():
            detail.setdefault(head, set()).update(tail.strip().lower().split())
    return base, detail


def f_marks(lost: ItemView, found: ItemView) -> Feature:
    if not lost.marks or not found.marks:
        return Feature("marks", 0.0, False, "", "no marks")
    a, da = _mark_sets(lost.marks)
    b, db = _mark_sets(found.marks)
    inter = a & b
    v = len(inter) / len(a | b)
    for head in inter:  # matching detail (same words on the sticker) firms it up
        if da.get(head) and db.get(head) and da[head] & db[head]:
            v = min(1.0, v + 0.3)
    if not inter:
        return Feature("marks", 0.0, True, "Different marks")
    return Feature("marks", clip01(v), True, f"{', '.join(sorted(inter)).capitalize()} in both")


def f_zone(lost: ItemView, found: ItemView, names: dict[str, str] | None = None, graph=None) -> Feature:
    h = zones.hops(lost.zone_id, found.zone_id, graph)
    v = math.exp(-h / ZONE_HOP_SCALE)
    n = names or {}
    a, b = n.get(lost.zone_id, lost.zone_id), n.get(found.zone_id, found.zone_id)
    if h == 0:
        detail = f"Lost and turned in at {a}"
    else:
        detail = f"Lost at {a}, turned in at {b} ({h} zone{'s' if h != 1 else ''} away)"
    return Feature("zone", clip01(v), True, detail)


def f_time(lost: ItemView, found: ItemView) -> Feature | None:
    """None means the hard gate excluded the pair."""
    t = found.occurred_from
    if t < lost.occurred_from:
        return None
    if t <= lost.occurred_to:
        return Feature("time", 1.0, True, "Turned in within the time you gave")
    gap_h = (t - lost.occurred_to).total_seconds() / 3600.0
    v = math.exp(-gap_h / TIME_DECAY_HOURS)
    when = f"{gap_h:.0f} hours" if gap_h < 48 else f"{gap_h / 24:.0f} days"
    return Feature("time", clip01(v), True, f"Turned in {when} after you last had it")


def compute_features(lost: ItemView, found: ItemView, zone_names: dict[str, str] | None = None, graph=None) -> list[Feature] | None:
    """All nine features in FEATURES order, or None when the time gate excludes the pair."""
    time_f = f_time(lost, found)
    if time_f is None:
        return None
    by_key = {
        "category": f_category(lost, found),
        "color": f_color(lost, found),
        "brand": f_brand(lost, found),
        "image": f_image(lost, found),
        "text": f_text(lost, found),
        "cross_modal": f_cross_modal(lost, found),
        "marks": f_marks(lost, found),
        "zone": f_zone(lost, found, zone_names, graph),
        "time": time_f,
    }
    return [by_key[k] for k in FEATURES]
