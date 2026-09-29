"""Synthetic lost/found pairs for the eval harness, from public photos (see scripts/fetch_seed_photos.py).

Each pair shares one latent object. The "lost" and "found" sides are different views of it:
photos get independent augmentations (crop, rotation, flip, exposure, blur, background shift) and the text is
generated from the latent attributes plus noise (dropped details, synonyms, typos, filler). Zones and times
come from plausible walks. Categories Open Images cannot supply (ID cards, keys, earbuds, wallets, chargers,
power banks) appear as text-only pairs.

Everything here is OPTIMISTIC: the same photo underlies both views and the text comes from the labels the
matcher is later scored against. Reports built from it are tagged `pairs: synthetic` and labelled as such.

    python -m eval.synthetic_pairs [--seed 0] [--text-only 24]
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import taxonomy  # noqa: E402  (after the path tweak)
from app.ml.matching import zones as zone_graph  # noqa: E402
from app.ml.vision import color  # noqa: E402

PHOTOS = ROOT / "data" / "seed"
OUT = ROOT / "eval" / "pairs" / "synthetic"
FIELDS = ["pair_id", "side", "image", "text", "zone", "timestamp", "category", "set"]

BRANDS = {
    "laptop": ["Dell", "HP", "Lenovo", "Apple", "Asus", "Acer"],
    "phone": ["Samsung", "Apple", "OnePlus", "Xiaomi", "Realme"],
    "tablet": ["Samsung", "Apple", "Lenovo"],
    "headphones": ["Sony", "Bose", "JBL", "boAt"],
    "earbuds": ["Apple", "Samsung", "boAt", "JBL", "OnePlus"],
    "backpack": ["Wildcraft", "Skybags", "American Tourister", "Nike", "Adidas"],
    "bottle": ["Milton", "Cello"],
    "watch": ["Casio", "Titan", "Fastrack", "Apple"],
    "calculator": ["Casio"],
    "spectacles": ["Ray-Ban"],
    "charger": ["Anker", "Samsung", "Apple"],
    "power_bank": ["Anker", "Xiaomi", "Realme"],
    "wallet": [],
    "keys": [],
    "id_card": [],
    "book": [],
    "notebook": ["Classmate", "Camlin"],
    "umbrella": [],
}
MARK_POOL = {
    "laptop": ["dent", "scratch", "sticker"], "phone": ["scratch", "cracked", "sticker"], "tablet": ["scratch", "cracked"],
    "bottle": ["dent", "sticker", "scratch"], "backpack": ["sticker", "scratch"], "watch": ["scratch", "engraved"],
    "headphones": ["scratch"], "calculator": ["scratch", "sticker"], "book": ["sticker"], "spectacles": ["scratch"],
    "earbuds": ["scratch"], "charger": ["scratch"], "power_bank": ["dent", "scratch", "sticker"], "wallet": ["scratch"],
    "keys": ["sticker"], "id_card": [], "notebook": ["sticker"], "umbrella": [],
}
STICKERS = ["crescent moon", "red star", "anime", "football", "black cat", "rainbow", "mountain"]
TEXT_ONLY_CATEGORIES = ["id_card", "keys", "earbuds", "wallet", "charger", "power_bank", "notebook"]
TEXT_ONLY_COLORS = ["black", "white", "blue", "red", "grey", "green", "brown", "silver", "navy", "pink"]
ZONE_WEIGHTS = {"z_library": 4, "z_canteen": 4, "z_block_a": 3, "z_block_b": 2, "z_gate": 2, "z_sports": 2, "z_hostel3": 2, "z_admin": 1}
FILLER_LOST = ["lost my", "i lost a", "missing:", "can't find my", "left my", ""]
FILLER_FOUND = ["found a", "found", "someone left a", "picked up a", ""]


def typo(word: str, rng: random.Random) -> str:
    if len(word) < 5 or rng.random() > 0.10:
        return word
    i = rng.randrange(1, len(word) - 2)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def synonym(category: str, rng: random.Random) -> str:
    syn = [s for s in taxonomy.categories()[category]["synonyms"] if " " not in s and "-" not in s and len(s) > 2]
    return rng.choice(syn) if syn and rng.random() < 0.35 else category.replace("_", " ")


def make_text(latent: dict, side: str, rng: random.Random, zone_alias: str) -> str:
    keep = 0.75 if side == "lost" else 0.60          # found reports say less
    parts: list[str] = []
    if latent["colors"] and rng.random() < keep:
        parts.append(latent["colors"][0])
    if latent["brand"] and rng.random() < keep:
        parts.append(latent["brand"])
    parts.append(synonym(latent["category"], rng) if rng.random() < 0.9 else "thing")
    text = " ".join(typo(p, rng) if p not in (latent["brand"],) else p for p in parts)
    marks = [m for m in latent["marks"] if rng.random() < keep]
    if marks:
        text += ", " + " and ".join(m.replace("sticker: ", "") + (" sticker" if m.startswith("sticker") else "") if m.startswith("sticker") else f"a {m}" for m in marks)
    if latent.get("serial") and side == "found" and rng.random() < 0.3:
        text += f", serial ending {latent['serial']}"
    filler = rng.choice(FILLER_LOST if side == "lost" else FILLER_FOUND)
    where = f" near {zone_alias}" if side == "found" and rng.random() < 0.5 else ""
    return re.sub(r"\s+", " ", f"{filler} {text}{where}").strip()


def augment(im: Image.Image, rng: random.Random, box: tuple[float, float, float, float] | None) -> Image.Image:
    w, h = im.size
    if box:  # crop that always keeps the object, then jitter the frame
        x, y, bw, bh = box
        x0, y0, x1, y1 = x * w, y * h, (x + bw) * w, (y + bh) * h
        pad = rng.uniform(0.02, 0.35)
        cx0, cy0 = max(0, x0 - pad * w * rng.random()), max(0, y0 - pad * h * rng.random())
        cx1, cy1 = min(w, x1 + pad * w * rng.random()), min(h, y1 + pad * h * rng.random())
        im = im.crop((int(cx0), int(cy0), int(cx1), int(cy1)))
    if rng.random() < 0.3:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im = im.rotate(rng.uniform(-12, 12), expand=True, fillcolor=(rng.randint(170, 240),) * 3)
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.75, 1.25))
    im = ImageEnhance.Contrast(im).enhance(rng.uniform(0.85, 1.2))
    im = ImageEnhance.Color(im).enhance(rng.uniform(0.8, 1.2))
    if rng.random() < 0.3:
        im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 1.4)))
    im.thumbnail((800, 800))
    return im


def pick_zone(rng: random.Random) -> str:
    zs, ws = zip(*ZONE_WEIGHTS.items())
    return rng.choices(zs, ws)[0]


def found_zone(lost_zone: str, rng: random.Random) -> str:
    r = rng.random()
    if r < 0.45:
        return lost_zone
    graph = zone_graph._graph()
    ring = {1: sorted(graph.get(lost_zone, [])), 2: [z for z in graph if zone_graph.hops(lost_zone, z, graph) == 2]}
    if r < 0.80 and ring[1]:
        return rng.choice(ring[1])
    if r < 0.95 and ring[2]:
        return rng.choice(ring[2])
    return pick_zone(rng)


def times(rng: random.Random, base: datetime) -> tuple[datetime, datetime, datetime]:
    start = base + timedelta(days=rng.randrange(0, 14), hours=rng.randrange(8, 20), minutes=rng.choice([0, 15, 30, 45]))
    end = start + timedelta(hours=rng.uniform(1, 6))
    if rng.random() < 0.25:
        found = start + (end - start) * rng.random()             # turned in while they were still looking
    else:
        found = end + timedelta(hours=min(72.0, rng.expovariate(1 / 12.0)))
    return start, end, found


def generate(seed: int = 0, text_only: int = 24) -> list[dict]:
    rng = random.Random(seed)
    (OUT / "imgs").mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows: list[dict] = []
    aliases = taxonomy.zone_aliases()

    latents: list[dict] = []
    with open(PHOTOS / "photos.csv") as f:
        for r in csv.DictReader(f):
            im = Image.open(PHOTOS / "photos" / r["image"]).convert("RGB")
            box = (float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"]))
            crop = np.asarray(im.crop((int(box[0] * im.width), int(box[1] * im.height), int((box[0] + box[2]) * im.width), int((box[1] + box[3]) * im.height))))
            colors = [c["name"] for c in color.dominant_colors(crop)]
            latents.append({"category": r["category"], "photo": im, "box": box, "colors": colors})
    for i in range(text_only):
        latents.append({"category": TEXT_ONLY_CATEGORIES[i % len(TEXT_ONLY_CATEGORIES)], "photo": None, "box": None, "colors": [rng.choice(TEXT_ONLY_COLORS)]})

    for i, lat in enumerate(latents):
        cat = lat["category"]
        brands = BRANDS.get(cat, [])
        pool = MARK_POOL.get(cat, [])
        marks = rng.sample(pool, k=min(len(pool), rng.choice([0, 1, 1, 2]))) if pool else []
        marks = [f"sticker: {rng.choice(STICKERS)}" if m == "sticker" else m for m in marks]
        latent = {
            "category": cat, "colors": lat["colors"][:2], "brand": rng.choice(brands) if brands and rng.random() < 0.7 else None,
            "marks": marks, "serial": f"{rng.randrange(16**4):04X}" if cat in ("laptop", "phone", "tablet", "power_bank") and rng.random() < 0.5 else None,
        }
        pid = f"P{i:03d}"
        zl = pick_zone(rng)
        zf = found_zone(zl, rng)
        start, end, found_t = times(rng, base)

        has_photo = lat["photo"] is not None
        lost_photo = has_photo and rng.random() < 0.5
        found_photo = has_photo and rng.random() < 0.8
        lost_text = (not lost_photo) or rng.random() < 0.85
        found_text = (not found_photo) or rng.random() < 0.6

        def photo_path(side: str, flag: bool) -> str:
            if not flag:
                return ""
            p = OUT / "imgs" / f"{pid}_{side}.jpg"
            augment(lat["photo"], random.Random(f"{seed}-{pid}-{side}"), lat["box"]).convert("RGB").save(p, quality=88)
            return str(p.relative_to(OUT))   # relative to the manifest, like a real manifest

        za = rng.choice(aliases.get(zl, [zl]))
        zb = rng.choice(aliases.get(zf, [zf]))
        rows.append({"pair_id": pid, "side": "lost", "image": photo_path("lost", lost_photo), "text": make_text(latent, "lost", rng, za) if lost_text else "",
                     "zone": zl, "timestamp": f"{start.isoformat()}/{end.isoformat()}", "category": cat, "set": "synthetic"})
        rows.append({"pair_id": pid, "side": "found", "image": photo_path("found", found_photo), "text": make_text(latent, "found", rng, zb) if found_text else "",
                     "zone": zf, "timestamp": found_t.isoformat(), "category": cat, "set": "synthetic"})
    return rows


def write(rows: list[dict]) -> Path:
    path = OUT / "manifest.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--text-only", type=int, default=24, help="extra text-only pairs for categories with no public photos")
    a = ap.parse_args()
    rows = generate(a.seed, a.text_only)
    p = write(rows)
    photos = sum(1 for r in rows if r["image"])
    print(f"wrote {len(rows) // 2} pairs ({photos} photos) to {p}")
