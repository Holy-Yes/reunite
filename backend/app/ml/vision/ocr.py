"""RapidOCR on the crop (and on the full image for suspected ID cards). Extracts brand text
(fuzzy against the brand gazetteer) and roll numbers (campus regex)."""
from __future__ import annotations

import os
import re
from functools import lru_cache

import cv2
import numpy as np
from rapidfuzz import fuzz

from ... import taxonomy
from ...config import get_settings
from .. import registry
from ..attrs import attr


@lru_cache
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    registry.note("ocr", "rapidocr-onnxruntime")
    threads = int(os.environ.get("OCR_THREADS", "1"))  # more threads were slower on a busy 8 GB laptop
    return RapidOCR(det_limit_type="max", det_limit_side_len=512, intra_op_num_threads=threads, inter_op_num_threads=1)


NO_TEXT_CATEGORIES = {"umbrella", "keys", "spectacles"}  # rarely carry printed brands: not worth seconds of OCR


def read_text(rgb: np.ndarray, max_side: int = 512) -> list[tuple[str, float]]:
    """[(line, confidence)] in reading order. The image is shrunk to `max_side` first: OCR cost grows
    with pixels, and brand text on a photographed object stays legible at 512. Empty in light mode."""
    if get_settings().light_ml:
        return []
    h, w = rgb.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        rgb = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    def run():
        result, _ = _engine()(np.ascontiguousarray(rgb[:, :, ::-1]))  # RapidOCR expects BGR
        return [(str(t), float(c)) for _, t, c in (result or [])]

    return registry.call_ml(run)


@lru_cache
def _brand_terms() -> dict[str, str]:
    terms: dict[str, str] = {}
    for brand, aliases in taxonomy.brands().items():
        for t in [brand, *aliases]:
            if len(t) >= 3:
                terms[t.lower()] = brand
    return terms


def parse_ocr(lines: list[tuple[str, float]]) -> dict:
    """{ brand?: Attr, serial?: Attr, roll_no?: str, text: str }."""
    text = " ".join(t for t, _ in lines)
    out: dict = {"text": text}
    if not lines:
        return out
    upper = text.upper()
    roll = re.search(get_settings().roll_no_regex, upper.replace(" ", ""))
    if roll:
        out["roll_no"] = roll.group(0)
        out["serial"] = attr(roll.group(0), 0.9, "ocr")

    words = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    best: tuple[float, str] = (0.0, "")
    for w in words:
        for term, brand in _brand_terms().items():
            s = fuzz.ratio(w, term)
            if s >= 90 and s > best[0]:
                best = (s, brand)
    if best[1]:
        out["brand"] = attr(best[1], min(0.9, best[0] / 100 * 0.9), "ocr")
    return out
