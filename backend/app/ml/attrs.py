"""The Attr shape shared by parser, vision, fusion and the API: { value, confidence, source, hidden? }."""
from __future__ import annotations

from typing import Any

SOURCES = ("photo", "text", "ocr", "user")


def attr(value: Any, confidence: float, source: str, hidden: bool | None = None) -> dict:
    a: dict = {"value": value, "confidence": round(float(confidence), 3), "source": source}
    if hidden:
        a["hidden"] = True
    return a


def noisy_or(*confidences: float) -> float:
    """Two independent sources agreeing raise confidence: 1 - prod(1 - c)."""
    p = 1.0
    for c in confidences:
        p *= 1.0 - max(0.0, min(1.0, c))
    return 1.0 - p
