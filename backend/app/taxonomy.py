"""The shared vocabulary: categories, groups, colors, marks, brands. One source of truth for the
text parser, the color namer, the feature extractor and `GET /taxonomy`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

LEX = Path(__file__).parent / "ml" / "text" / "lexicons"


def _load(name: str) -> dict:
    with open(LEX / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def categories() -> dict[str, dict]:
    return _load("categories.yaml")["categories"]


@lru_cache
def category_names() -> list[str]:
    return list(categories())


@lru_cache
def generic_terms() -> dict[str, dict]:
    return _load("categories.yaml")["generic"]


@lru_cache
def materials() -> list[str]:
    return _load("categories.yaml")["materials"]


def category_group(category: str | None) -> str | None:
    if not category:
        return None
    return categories().get(category, {}).get("group")


@lru_cache
def palette() -> dict[str, dict]:
    return _load("colors.yaml")["colors"]


@lru_cache
def marks() -> dict[str, list[str]]:
    return _load("marks.yaml")["marks"]


@lru_cache
def brands() -> dict[str, list[str]]:
    return _load("brands.yaml")["brands"]


@lru_cache
def zone_aliases() -> dict[str, list[str]]:
    return _load("zones.yaml")["zones"]


def taxonomy_payload() -> dict:
    """The shape returned by GET /taxonomy."""
    return {
        "categories": [{"id": k, "group": v["group"]} for k, v in categories().items()],
        "brands": sorted(brands()),
        "colors": [{"name": k, "hex": v["hex"]} for k, v in palette().items()],
        "marks": list(marks()),
    }
