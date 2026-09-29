#!/usr/bin/env python
"""Download ~100 Open Images validation photos of campus-style objects for seed data and synthetic eval pairs.

    python scripts/fetch_seed_photos.py [--per-class 10]

Downloads: the class list (12 KB), the validation box annotations (25 MB, cached in .cache/), and about 100
JPEGs (around 200 KB each) from the public Open Images bucket. Open Images images are CC BY 2.0 (licensing is
per image); annotations are CC BY 4.0. Nothing here is personal data collected by us.

Writes data/seed/photos/<category>_<n>.jpg and data/seed/photos.csv (image, category, x, y, w, h, source_id).
Only categories Open Images can supply are covered; ID cards, keys, earbuds, wallets, chargers and power banks have
no boxable class, so the synthetic eval covers them with text only (see eval/README.md).
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "openimages"
OUT = ROOT / "data" / "seed"
BASE = "https://storage.googleapis.com/openimages/v5"
IMG = "https://open-images-dataset.s3.amazonaws.com/validation/{}.jpg"

# Open Images class name -> campus category
CLASSES = {
    "Laptop": "laptop",
    "Mobile phone": "phone",
    "Tablet computer": "tablet",
    "Backpack": "backpack",
    "Bottle": "bottle",
    "Book": "book",
    "Umbrella": "umbrella",
    "Headphones": "headphones",
    "Glasses": "spectacles",
    "Watch": "watch",
    "Calculator": "calculator",
}


def get(url: str, dest: Path | None = None) -> bytes:
    if dest is not None and dest.exists():
        return dest.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "reunite-seed/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    names = {}
    for row in csv.reader(io.StringIO(get(f"{BASE}/class-descriptions-boxable.csv", CACHE / "classes.csv").decode())):
        names[row[1]] = row[0]
    label_of = {names[c]: cat for c, cat in CLASSES.items() if c in names}
    print("classes:", {c: names.get(c) for c in CLASSES})

    print("reading box annotations (25 MB)...", flush=True)
    text = get(f"{BASE}/validation-annotations-bbox.csv", CACHE / "val-bbox.csv").decode()
    per: dict[str, list[tuple]] = {c: [] for c in label_of.values()}
    relaxed: dict[str, list[tuple]] = {c: [] for c in label_of.values()}
    seen_images: dict[str, int] = {}
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        seen_images[r["ImageID"]] = seen_images.get(r["ImageID"], 0) + 1
    for r in rows:
        cat = label_of.get(r["LabelName"])
        if not cat or r["IsGroupOf"] == "1" or r["IsOccluded"] == "1" or r["IsTruncated"] == "1":
            continue
        x0, x1, y0, y1 = (float(r[k]) for k in ("XMin", "XMax", "YMin", "YMax"))
        area = (x1 - x0) * (y1 - y0)
        box = (r["ImageID"], x0, y0, x1 - x0, y1 - y0)
        # one clear, fairly large object, so a "lost" and "found" view of it are about the same thing
        if area >= 0.25 and seen_images[r["ImageID"]] <= 3:
            per[cat].append(box)
        elif area >= 0.10 and seen_images[r["ImageID"]] <= 6:
            relaxed[cat].append(box)  # fallback for sparse classes such as umbrella

    chosen: list[tuple[str, str, float, float, float, float]] = []
    for cat, cands in per.items():
        rng.shuffle(cands)
        fallback = relaxed[cat]
        rng.shuffle(fallback)
        uniq: dict[str, tuple] = {}
        for c in cands + (fallback if len(cands) < args.per_class else []):
            uniq.setdefault(c[0], c)
        for c in list(uniq.values())[: args.per_class]:
            chosen.append((cat, *c))
    print(f"downloading {len(chosen)} photos...", flush=True)

    photos = OUT / "photos"
    photos.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    jobs = []
    for cat, iid, x, y, w, h in chosen:
        counts[cat] = counts.get(cat, 0) + 1
        jobs.append((cat, iid, x, y, w, h, photos / f"{cat}_{counts[cat]:02d}.jpg"))

    def fetch(job):
        cat, iid, x, y, w, h, path = job
        try:
            data = get(IMG.format(iid))
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((1024, 1024))
            im.save(path, "JPEG", quality=88)
            return (path.name, cat, round(x, 4), round(y, 4), round(w, 4), round(h, 4), iid)
        except Exception as e:  # noqa: BLE001
            print("  skipped", iid, e, file=sys.stderr)
            return None

    with ThreadPoolExecutor(8) as ex:
        done = [r for r in ex.map(fetch, jobs) if r]
    with open(OUT / "photos.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["image", "category", "x", "y", "w", "h", "source_id"])
        wr.writerows(sorted(done))
    by = {}
    for r in done:
        by[r[1]] = by.get(r[1], 0) + 1
    print(f"saved {len(done)} photos to {photos}", by)
    return 0


if __name__ == "__main__":
    sys.exit(main())
