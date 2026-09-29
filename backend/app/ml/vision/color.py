"""Deterministic color naming: GrabCut the object, k-means in CIELAB, name clusters by CIEDE2000."""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np
from sklearn.cluster import KMeans

from ... import taxonomy


# ---- color science ------------------------------------------------------------


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """(...,3) uint8 or 0-255 floats -> CIELAB (L 0-100). Uses OpenCV's float conversion."""
    arr = np.asarray(rgb, dtype=np.float32).reshape(-1, 1, 3) / 255.0
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).reshape(-1, 3)
    return lab.reshape(np.asarray(rgb).shape)


def hex_to_rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 (Sharma et al. 2005). Broadcasts over leading dimensions."""
    l1, a1, b1 = (lab1[..., i].astype(np.float64) for i in range(3))
    l2, a2, b2 = (lab2[..., i].astype(np.float64) for i in range(3))
    c1, c2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cbar7 = ((c1 + c2) / 2.0) ** 7
    g = 0.5 * (1.0 - np.sqrt(cbar7 / (cbar7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dl = l2 - l1
    dc = c2p - c1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, dh)
    dh = np.where(dh < -180, dh + 360, dh)
    dh = np.where(c1p * c2p == 0, 0.0, dh)
    dhp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh) / 2.0)

    lbar = (l1 + l2) / 2.0
    cbar = (c1p + c2p) / 2.0
    hsum = h1p + h2p
    hbar = np.where(
        c1p * c2p == 0,
        hsum,
        np.where(np.abs(h1p - h2p) <= 180, hsum / 2.0, np.where(hsum < 360, (hsum + 360) / 2.0, (hsum - 360) / 2.0)),
    )
    t = (
        1
        - 0.17 * np.cos(np.radians(hbar - 30))
        + 0.24 * np.cos(np.radians(2 * hbar))
        + 0.32 * np.cos(np.radians(3 * hbar + 6))
        - 0.20 * np.cos(np.radians(4 * hbar - 63))
    )
    d_theta = 30 * np.exp(-(((hbar - 275) / 25) ** 2))
    rc = 2 * np.sqrt(cbar**7 / (cbar**7 + 25.0**7))
    sl = 1 + (0.015 * (lbar - 50) ** 2) / np.sqrt(20 + (lbar - 50) ** 2)
    sc = 1 + 0.045 * cbar
    sh = 1 + 0.015 * cbar * t
    rt = -np.sin(np.radians(2 * d_theta)) * rc
    return np.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dhp / sh) ** 2 + rt * (dc / sc) * (dhp / sh))


@lru_cache
def _palette() -> tuple[list[str], np.ndarray, list[str]]:
    names = list(taxonomy.palette())
    hexes = [taxonomy.palette()[n]["hex"] for n in names]
    rgb = np.array([hex_to_rgb(h) for h in hexes], dtype=np.float32)
    return names, rgb_to_lab(rgb), hexes


def name_color(lab: np.ndarray) -> tuple[str, float]:
    """Nearest palette color to one Lab value, and its CIEDE2000 distance."""
    names, plab, _ = _palette()
    d = ciede2000(np.asarray(lab)[None, :], plab)
    i = int(np.argmin(d))
    return names[i], float(d[i])


def palette_delta_e(a: str, b: str) -> float:
    names, plab, _ = _palette()
    return float(ciede2000(plab[names.index(a)], plab[names.index(b)]))


# ---- image -> named colors ------------------------------------------------------


def _object_pixels(rgb: np.ndarray, box: tuple[float, float, float, float] | None) -> np.ndarray:
    h, w = rgb.shape[:2]
    if box:
        x, y, bw, bh = box
        x0, y0 = max(int(x * w), 0), max(int(y * h), 0)
        x1, y1 = min(int((x + bw) * w), w), min(int((y + bh) * h), h)
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            rgb = rgb[y0:y1, x0:x1]
    scale = 160.0 / max(rgb.shape[:2])
    if scale < 1:
        rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = rgb.shape[:2]
    if h < 12 or w < 12:
        return rgb.reshape(-1, 3)

    # Center-weighted rectangle: assume the object sits in the middle 70% of its crop.
    mx, my = max(int(w * 0.15), 1), max(int(h * 0.15), 1)
    rect = (mx, my, max(w - 2 * mx, 1), max(h - 2 * my, 1))
    mask = np.zeros((h, w), np.uint8)
    try:
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
        fg = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    except cv2.error:
        fg = np.zeros((h, w), bool)
    if fg.mean() < 0.05:  # GrabCut found nothing usable: fall back to the central rectangle
        fg = np.zeros((h, w), bool)
        fg[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]] = True
    return rgb[fg]


def dominant_colors(
    rgb: np.ndarray,
    box: tuple[float, float, float, float] | None = None,
    k: int = 3,
    min_share: float = 0.15,
    max_colors: int = 2,
) -> list[dict]:
    """Up to two named colors: [{name, share, delta_e, hex}], largest first."""
    px = _object_pixels(rgb, box)
    if len(px) == 0:
        return []
    if len(px) > 4000:
        px = px[np.random.default_rng(0).choice(len(px), 4000, replace=False)]
    lab = rgb_to_lab(px)
    k = max(1, min(k, len(np.unique(px, axis=0))))
    km = KMeans(n_clusters=k, n_init=3, random_state=0).fit(lab)
    shares = np.bincount(km.labels_, minlength=k) / len(lab)

    merged: dict[str, dict] = {}
    for centre, share in zip(km.cluster_centers_, shares):
        name, de = name_color(centre)
        m = merged.setdefault(name, {"name": name, "share": 0.0, "delta_e": de, "_w": 0.0})
        m["delta_e"] = (m["delta_e"] * m["_w"] + de * share) / (m["_w"] + share) if m["_w"] + share else de
        m["share"] += float(share)
        m["_w"] += float(share)
    _, _, hexes = _palette()
    names = list(taxonomy.palette())
    out = []
    for m in sorted(merged.values(), key=lambda v: -v["share"]):
        if m["share"] >= min_share:
            out.append({"name": m["name"], "share": round(m["share"], 3), "delta_e": round(m["delta_e"], 2), "hex": hexes[names.index(m["name"])]})
    return out[:max_colors] or [
        {"name": max(merged.values(), key=lambda v: v["share"])["name"], "share": 1.0, "delta_e": 0.0, "hex": "#000000"}
    ][:1]
