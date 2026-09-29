#!/usr/bin/env python
"""Fetch the pretrained models the app needs (one time, needs network).

    yolo11n            ~6 MB    backend/weights/yolo11n.pt
    CLIP ViT-B/32     ~350 MB   .cache/hf      (open_clip, OpenAI weights)
    MiniLM-L6         ~90 MB    .cache/hf      (sentence-transformers)
    spaCy en_core_web_sm ~12 MB  installed with `python -m spacy download en_core_web_sm`
    RapidOCR                    ships inside the rapidocr-onnxruntime wheel (~15 MB)

Trained weights from the compute bucket (detector.pt, heads.pt, calibration.json) are dropped into
backend/weights/ by hand and picked up automatically; this script never touches them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("JWT_SECRET", "download-only")

from app.ml import registry  # noqa: E402

registry.setup_cache_dirs()
WEIGHTS = ROOT / "backend" / "weights"
WEIGHTS.mkdir(parents=True, exist_ok=True)


def step(name: str) -> None:
    print(f"\n== {name}", flush=True)


def yolo() -> None:
    step("YOLO11n (COCO)")
    target = WEIGHTS / "yolo11n.pt"
    if target.exists():
        print("already there:", target)
        return
    from ultralytics import YOLO

    cwd = os.getcwd()
    os.chdir(WEIGHTS)  # ultralytics downloads next to the working directory
    try:
        YOLO("yolo11n.pt")
    finally:
        os.chdir(cwd)
    print("saved", target, f"({target.stat().st_size / 1e6:.1f} MB)")


def clip() -> None:
    step("CLIP ViT-B/32 (OpenAI weights)")
    import open_clip

    open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
    open_clip.get_tokenizer("ViT-B-32")
    print("ok")


def minilm() -> None:
    step("all-MiniLM-L6-v2")
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("ok")


def spacy_model() -> None:
    step("spaCy en_core_web_sm")
    import importlib.util

    if importlib.util.find_spec("en_core_web_sm"):
        print("installed")
    else:
        print("missing: run  python -m spacy download en_core_web_sm")


def ocr() -> None:
    step("RapidOCR")
    from rapidocr_onnxruntime import RapidOCR

    RapidOCR()
    print("ok (models ship with the package)")


if __name__ == "__main__":
    which = sys.argv[1:] or ["yolo", "clip", "minilm", "spacy", "ocr"]
    table = {"yolo": yolo, "clip": clip, "minilm": minilm, "spacy": spacy_model, "ocr": ocr}
    for w in which:
        table[w]()
    print("\nAll set.")
