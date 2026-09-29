"""Turn "black Dell laptop, small dent on the lid" into {category, brand, colors, marks, serial}.

spaCy supplies the tokenizer and an EntityRuler over the gazetteers in `lexicons/*.yaml` (longest
phrase wins). A fuzzy pass with rapidfuzz then catches typos. Confidence: exact gazetteer hit 0.95,
fuzzy hit 0.70, generic family term ("bag") 0.4 to 0.6.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from rapidfuzz import fuzz, process

from ... import taxonomy
from ...config import get_settings
from ..attrs import attr

EXACT = 0.95
FUZZY = 0.70

STOP = {
    "a", "an", "the", "of", "on", "in", "at", "with", "and", "my", "small", "big", "large", "little",
    "tiny", "old", "new", "has", "have", "had", "is", "was", "it", "its", "some", "few", "there",
    "shiny", "dark", "light", "bright", "faded", "worn", "another", "one", "two", "that", "this",
}

SERIAL_RE = re.compile(
    r"(?:serial|s/n|s\.n\.?|sn|imei|model)\s*(?:number|no\.?|#|:|ending(?:\s+in)?|ends\s+with|is)?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-]{3,})",
    re.IGNORECASE,
)


@dataclass
class ParsedText:
    category: dict | None = None
    brand: dict | None = None
    colors: list[dict] = field(default_factory=list)
    marks: list[dict] = field(default_factory=list)
    serial: dict | None = None
    zone_hint: dict | None = None  # {"value": zone_id, "confidence": ...}
    alt_categories: list[str] = field(default_factory=list)

    def to_attributes(self) -> dict:
        out: dict = {"colors": self.colors, "marks": self.marks}
        if self.category:
            out["category"] = self.category
        if self.brand:
            out["brand"] = self.brand
        if self.serial:
            out["serial"] = self.serial
        return out


# ---- gazetteer ---------------------------------------------------------------


@lru_cache
def _vocab() -> dict[str, tuple[str, str, float]]:
    """lowercase phrase -> (label, canonical value, confidence)."""
    v: dict[str, tuple[str, str, float]] = {}
    for cat, spec in taxonomy.categories().items():
        v[cat.replace("_", " ")] = ("CATEGORY", cat, EXACT)
        for s in spec["synonyms"]:
            v[s.lower()] = ("CATEGORY", cat, EXACT)
    for term, spec in taxonomy.generic_terms().items():
        v.setdefault(term.lower(), ("CATEGORY", spec["category"], spec["confidence"]))
    for name, spec in taxonomy.palette().items():
        for s in spec["synonyms"]:
            v[s.lower()] = ("COLOR", name, EXACT)
    for mark, syns in taxonomy.marks().items():
        for s in syns:
            v[s.lower()] = ("MARK", mark, EXACT)
    for brand, aliases in taxonomy.brands().items():
        v[brand.lower()] = ("BRAND", brand, EXACT)
        for a in aliases:
            # An alias such as "macbook" names a product line: it is a category, so do not let it
            # also claim to be the brand unless it is the brand itself.
            v.setdefault(a.lower(), ("BRAND", brand, EXACT if a.lower() == brand.lower() else 0.85))
    return v


@lru_cache
def _nlp():
    nlp = spacy.blank("en")
    ruler = nlp.add_pipe("entity_ruler", config={"phrase_matcher_attr": "LOWER", "overwrite_ents": True})
    patterns = [{"label": label, "pattern": phrase, "id": f"{value}|{conf}"} for phrase, (label, value, conf) in _vocab().items()]
    ruler.add_patterns(patterns)  # type: ignore[attr-defined]
    return nlp


@lru_cache
def _single_words() -> dict[str, tuple[str, str, float]]:
    return {p: t for p, t in _vocab().items() if " " not in p and "-" not in p and len(p) >= 4}


@lru_cache
def _zone_phrases() -> list[tuple[str, str]]:
    rows = [(alias.lower(), zid) for zid, aliases in taxonomy.zone_aliases().items() for alias in aliases]
    return sorted(rows, key=lambda r: -len(r[0]))  # longest alias first


# ---- parsing -----------------------------------------------------------------


def parse_text(text: str | None) -> ParsedText:
    out = ParsedText()
    if not text or not text.strip():
        return out
    doc = _nlp()(text)

    categories: list[tuple[float, int, str]] = []  # (confidence, -position, value)
    brands: list[tuple[float, int, str]] = []
    covered: set[int] = set()

    for ent in doc.ents:
        value, conf_s = ent.ent_id_.rsplit("|", 1)
        conf = float(conf_s)
        covered.update(range(ent.start, ent.end))
        if ent.label_ == "CATEGORY":
            categories.append((conf, -ent.start, value))
        elif ent.label_ == "BRAND":
            brands.append((conf, -ent.start, value))
        elif ent.label_ == "COLOR":
            if all(c["value"] != value for c in out.colors):
                out.colors.append(attr(value, conf, "text"))
        elif ent.label_ == "MARK":
            mark_value = _mark_with_detail(doc, ent) if value == "sticker" else value
            if all(m["value"].split(":")[0] != value for m in out.marks):
                out.marks.append(attr(mark_value, conf, "text"))

    # Fuzzy pass over tokens no phrase claimed: "lapto", "sticer".
    singles = _single_words()
    for tok in doc:
        if tok.i in covered or not tok.is_alpha or len(tok.text) < 4 or tok.lower_ in STOP:
            continue
        low = tok.lower_
        hit = process.extractOne(low, singles.keys(), scorer=fuzz.ratio, score_cutoff=90)
        if not hit or hit[0][0] != low[0]:
            continue
        label, value, _ = singles[hit[0]]
        if label == "CATEGORY":
            categories.append((FUZZY, -tok.i, value))
        elif label == "BRAND":
            brands.append((FUZZY, -tok.i, value))
        elif label == "COLOR" and all(c["value"] != value for c in out.colors):
            out.colors.append(attr(value, FUZZY, "text"))
        elif label == "MARK" and all(m["value"].split(":")[0] != value for m in out.marks):
            out.marks.append(attr(value, FUZZY, "text"))

    if categories:
        categories.sort(key=lambda t: (-t[0], -t[1]))  # highest confidence, then first mention
        conf, _, value = categories[0]
        out.category = attr(value, conf, "text")
        out.alt_categories = [c[2] for c in categories[1:] if c[2] != value]
    if brands:
        brands.sort(key=lambda t: (-t[0], -t[1]))
        out.brand = attr(brands[0][2], brands[0][0], "text")
    out.colors = out.colors[:2]

    out.serial = _serial(text)
    out.zone_hint = _zone(text)
    return out


def _mark_with_detail(doc, ent) -> str:
    """sticker -> "sticker: rose". Prefers the words after "of"/"with"/"saying", else up to two words before it."""
    j = ent.end
    if j < len(doc) and doc[j].lower_ in ("of", "with", "saying", "reading", "showing"):
        j += 1
        after: list[str] = []
        while j < len(doc) and len(after) < 3 and doc[j].is_alpha and doc[j].lower_ not in ("on", "and", "at", "in"):
            if doc[j].lower_ not in ("a", "an", "the"):
                after.append(doc[j].lower_)
            j += 1
        if after:
            return "sticker: " + " ".join(after)
    before: list[str] = []
    i = ent.start - 1
    while i >= 0 and len(before) < 2:
        t = doc[i]
        if not t.is_alpha or t.lower_ in STOP or t.ent_type_:  # any gazetteer word (a color, a category) is not a detail
            break
        before.insert(0, t.lower_)
        i -= 1
    return "sticker: " + " ".join(before) if before else "sticker"


def _serial(text: str) -> dict | None:
    roll = re.search(get_settings().roll_no_regex, text.upper())
    if roll:
        return attr(roll.group(0), EXACT, "text")
    m = SERIAL_RE.search(text)
    if m:
        cand = m.group(1).upper()
        if any(ch.isdigit() for ch in cand):  # "serial number ending" must carry digits to be a serial
            return attr(cand, 0.9, "text")
    return None


def _zone(text: str) -> dict | None:
    low = " " + re.sub(r"[^a-z0-9 ]", " ", text.lower()) + " "
    low = re.sub(r"\s+", " ", low)
    for alias, zid in _zone_phrases():
        if f" {alias} " in low:
            return {"value": zid, "confidence": EXACT}
    return None
