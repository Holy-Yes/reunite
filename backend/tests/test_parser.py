import pytest

from app.ml.text.parser import parse_text


def test_reference_case():
    p = parse_text("black Dell laptop, small dent on the lid")
    assert p.category["value"] == "laptop" and p.category["confidence"] == 0.95
    assert p.brand["value"] == "Dell"
    assert [c["value"] for c in p.colors] == ["black"]
    assert [m["value"] for m in p.marks] == ["dent"]
    assert all(a["source"] == "text" for a in [p.category, p.brand, *p.colors, *p.marks])


def test_synonyms_map_to_categories():
    assert parse_text("lost my macbook").category["value"] == "laptop"
    assert parse_text("found some airpods near the gym").category["value"] == "earbuds"
    assert parse_text("water flask, steel").category["value"] == "bottle"
    assert parse_text("my specs").category["value"] == "spectacles"


def test_generic_family_word_gets_lower_confidence():
    p = parse_text("a red bag")
    assert p.category["value"] == "backpack" and p.category["confidence"] < 0.95


def test_longest_phrase_wins():
    assert parse_text("black laptop bag").category["value"] == "backpack"
    assert parse_text("notebook computer").category["value"] == "laptop"
    assert parse_text("paper notebook").category["value"] == "notebook"


def test_navy_is_its_own_color_and_gray_is_grey():
    assert [c["value"] for c in parse_text("navy blue umbrella").colors] == ["navy"]
    assert [c["value"] for c in parse_text("a gray tablet").colors] == ["grey"]


def test_two_colors_at_most():
    assert len(parse_text("red white and blue backpack").colors) == 2


def test_marks_and_sticker_detail():
    p = parse_text("scratched phone with a crescent moon sticker and a crack")
    values = {m["value"] for m in p.marks}
    assert "scratch" in values and "cracked" in values and "sticker: crescent moon" in values


def test_sticker_of_something():
    assert parse_text("backpack with a sticker of a rose").marks[0]["value"] == "sticker: rose"


def test_roll_number_and_serial_regexes():
    assert parse_text("found id card 21071A0542").serial["value"] == "21071A0542"
    assert parse_text("laptop serial ending 4F2A").serial["value"] == "4F2A"
    assert parse_text("serial number ending in soon") .serial is None  # no digits, not a serial


def test_typos_get_fuzzy_confidence():
    p = parse_text("lapto with a scratched screan")
    assert p.category["value"] == "laptop" and p.category["confidence"] == 0.70


def test_zone_hint():
    assert parse_text("left it at the central library").zone_hint["value"] == "z_library"
    assert parse_text("somewhere at the canteen").zone_hint["value"] == "z_canteen"
    assert parse_text("no place mentioned").zone_hint is None


def test_empty_and_long_text():
    assert parse_text("").category is None and parse_text(None).colors == []
    long = "Black Dell laptop with a small dent on the lid, a crescent moon sticker, and a grey sleeve, left at the library reading room around lunch on Tuesday after the exam"
    p = parse_text(long)
    assert p.category["value"] == "laptop" and p.zone_hint["value"] == "z_library"


def test_milton_bottle():
    p = parse_text("blue steel water bottle, Milton")
    assert p.category["value"] == "bottle" and p.brand["value"] == "Milton" and [c["value"] for c in p.colors] == ["blue"]
