"""Object detection. COCO YOLO11n by default; `weights/detector.pt` (fine-tuned on campus classes)
is loaded automatically when present. Categories COCO does not know fall back to CLIP zero-shot on
the full image (see attributes.py)."""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from PIL import Image

from ...config import get_settings
from .. import registry

COCO_TO_CAMPUS = {
    "laptop": "laptop",
    "cell phone": "phone",
    "backpack": "backpack",
    "handbag": "backpack",
    "bottle": "bottle",
    "book": "book",
    "umbrella": "umbrella",
}


@lru_cache
def _yolo():
    registry.setup_cache_dirs()
    from ultralytics import YOLO

    weights = get_settings().weights_path
    trained = weights / "detector.pt"
    if trained.exists():
        model = YOLO(str(trained))
        registry.note("detector", "fine-tuned detector.pt")
        classes = None
        card = weights / "model_card.json"
        if card.exists():
            classes = json.loads(card.read_text()).get("detector_classes")
        return model, classes or {int(k): v for k, v in model.names.items()}, True
    model = YOLO(str(weights / "yolo11n.pt"))
    registry.note("detector", "yolo11n (COCO) + CLIP zero-shot for other classes")
    return model, {int(k): v for k, v in model.names.items()}, False


def detect(img: Image.Image, conf: float = 0.25) -> list[dict]:
    """[{label, confidence, box: [x, y, w, h] in 0..1}] for campus categories only."""
    if get_settings().light_ml:
        registry.note("detector", "light (none)")
        return []

    def run():
        model, names, trained = _yolo()
        res = model.predict(np.asarray(img.convert("RGB")), conf=conf, verbose=False, device=registry.device() if registry.device() != "mps" else "cpu")[0]
        w, h = img.size
        out = []
        for b in res.boxes:
            raw = names[int(b.cls)]
            label = raw if trained else COCO_TO_CAMPUS.get(raw)
            if not label:
                continue
            x0, y0, x1, y1 = (float(v) for v in b.xyxy[0])
            out.append({"label": label, "confidence": round(float(b.conf), 3), "box": [round(x0 / w, 4), round(y0 / h, 4), round((x1 - x0) / w, 4), round((y1 - y0) / h, 4)]})
        return sorted(out, key=lambda d: -d["confidence"] * d["box"][2] * d["box"][3])

    return registry.call_ml(run)


def primary_crop(detections: list[dict]) -> dict | None:
    """Highest confidence x area detection, else None (the caller then uses the full image)."""
    return detections[0] if detections else None
