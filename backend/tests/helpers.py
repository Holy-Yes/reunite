from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import Image

from app.ml.matching.features import ItemView

T0 = datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc)


def view(id: str = "x", kind: str = "lost", **kw) -> ItemView:  # noqa: A002
    base = dict(zone_id="z_library", occurred_from=T0, occurred_to=T0 + timedelta(hours=4))
    if kind == "found":
        base.update(occurred_from=T0 + timedelta(hours=6), occurred_to=T0 + timedelta(hours=6))
    base.update(kw)
    return ItemView(id=id, kind=kind, **base)


def unit(seed: int, dim: int = 512) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def png_bytes(color=(30, 30, 30), size=(240, 180)) -> bytes:
    im = Image.new("RGB", size, color)
    # a lighter rectangle so GrabCut has something to find
    for x in range(60, 180):
        for y in range(45, 135):
            im.putpixel((x, y), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
