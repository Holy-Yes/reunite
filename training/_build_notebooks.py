"""Regenerates the four notebooks in this folder from the cell lists below.

    python training/_build_notebooks.py

Notebooks are JSON, which reviews badly, so the source of truth is this file. Every code cell is
syntax-checked on build (lines starting with ! or % are shell/magic and are skipped).
"""
from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent


def md(text: str) -> dict:
    return {"cell_type": "markdown", "id": uuid.uuid4().hex[:8], "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "id": uuid.uuid4().hex[:8], "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)}


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
            "colab": {"provenance": []},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def check(name: str, nb: dict) -> None:
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        src = "".join(line for line in c["source"] if not line.lstrip().startswith(("!", "%")))
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise SystemExit(f"{name} cell {i}: {e}")


CLASSES = """CLASSES = [
    "id_card", "laptop", "phone", "tablet", "earbuds", "headphones", "charger", "power_bank", "wallet",
    "keys", "backpack", "bottle", "book", "notebook", "spectacles", "watch", "umbrella", "calculator",
]  # same order and names as backend/app/ml/text/lexicons/categories.yaml"""

# ---------------------------------------------------------------------------------------------
NB01 = [
    md("""
# 01 Build the detection dataset

**Compute bucket: run on Colab or Kaggle (CPU is fine, about 20 minutes, needs ~5 GB of Drive).**

Builds a YOLO-format dataset for ~18 campus classes from public sources, plus any photos you took yourself, and writes
`reunite_dataset.zip` to Drive. Notebook `02` trains on it.

Where the classes come from:

| Class | Source |
|---|---|
| laptop, phone, tablet, headphones, backpack, bottle, book, spectacles, watch, umbrella, calculator | Open Images V7 (boxes, CC BY 2.0 images) |
| earbuds, charger, power_bank, wallet, keys, notebook | Open Images has no clean class. Use LVIS/Objects365 names below if your FiftyOne version has them, and top up with your own photos |
| id_card | no public source. Photograph 50+ real or dummy cards (never real people's cards on shared drives) |

**Your own photos** go in `MyDrive/reunite/own/<class>/*.jpg` with a YOLO `.txt` label next to each (label with CVAT,
Roboflow, or `labelImg`). Even 30 per weak class helps a lot.
"""),
    code("""
!pip -q install fiftyone ultralytics pyyaml pillow
"""),
    code(f"""
from google.colab import drive
drive.mount("/content/drive")

import os, random, shutil, json, zipfile
from pathlib import Path
import yaml

{CLASSES}

WORK = Path("/content/work"); WORK.mkdir(exist_ok=True)
OUT = WORK / "dataset"
OWN = Path("/content/drive/MyDrive/reunite/own")
DEST = Path("/content/drive/MyDrive/reunite"); DEST.mkdir(parents=True, exist_ok=True)
PER_CLASS = 400          # Open Images images per class before de-duplication
VAL_SHARE = 0.15
random.seed(0)
"""),
    code("""
# campus class -> label names in the source datasets
OPEN_IMAGES = {
    "laptop": ["Laptop"], "phone": ["Mobile phone"], "tablet": ["Tablet computer"], "headphones": ["Headphones"],
    "backpack": ["Backpack"], "bottle": ["Bottle"], "book": ["Book"], "spectacles": ["Glasses"],
    "watch": ["Watch"], "umbrella": ["Umbrella"], "calculator": ["Calculator"],
}
LVIS = {  # only used if your FiftyOne zoo has 'lvis'; skipped quietly otherwise
    "earbuds": ["earphone"], "charger": ["charger"], "power_bank": ["battery"], "wallet": ["wallet"],
    "keys": ["key"], "notebook": ["notebook"],
}
"""),
    code("""
import fiftyone as fo
import fiftyone.zoo as foz

def load(source, mapping, split):
    names = sorted({n for v in mapping.values() for n in v})
    try:
        ds = foz.load_zoo_dataset(source, split=split, label_types=["detections"], classes=names,
                                  max_samples=PER_CLASS * max(len(mapping), 1), dataset_name=f"reunite_{source}_{split}", drop_existing_dataset=True)
    except Exception as e:                       # noqa: BLE001
        print("skipping", source, "->", e); return None
    back = {n: c for c, ns in mapping.items() for n in ns}
    for sample in ds:
        keep = []
        for det in sample.ground_truth.detections:
            if det.label not in back or getattr(det, "IsGroupOf", False):   # skip other classes and "a crowd of X" boxes
                continue
            det.label = back[det.label]
            keep.append(det)
        sample.ground_truth.detections = keep
        sample.save()
    return ds.match(fo.ViewField("ground_truth.detections").length() > 0)

parts = [p for p in (load("open-images-v7", OPEN_IMAGES, "train"), load("open-images-v7", OPEN_IMAGES, "validation"), load("lvis", LVIS, "train")) if p is not None]
print([len(p) for p in parts])
"""),
    code("""
# write YOLO layout: images/{train,val}, labels/{train,val}
for split in ("train", "val"):
    (OUT / "images" / split).mkdir(parents=True, exist_ok=True); (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

def write_sample(img_path, dets, split, tag):
    stem = f"{tag}_{Path(img_path).stem}"
    shutil.copy(img_path, OUT / "images" / split / f"{stem}.jpg")
    lines = []
    for label, (x, y, w, h) in dets:
        if label in CLASSES:
            lines.append(f"{CLASSES.index(label)} {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}")
    (OUT / "labels" / split / f"{stem}.txt").write_text("\\n".join(lines))

n = 0
for i, view in enumerate(parts):
    for s in view.iter_samples(progress=True):
        split = "val" if random.random() < VAL_SHARE else "train"
        write_sample(s.filepath, [(d.label, d.bounding_box) for d in s.ground_truth.detections], split, f"src{i}"); n += 1
print("public images:", n)

# your own photos: own/<class>/<name>.jpg + own/<class>/<name>.txt (YOLO format, class index per CLASSES)
own = 0
for cls_dir in OWN.glob("*"):
    for img in cls_dir.glob("*.jpg"):
        txt = img.with_suffix(".txt")
        if not txt.exists():
            continue
        split = "val" if random.random() < VAL_SHARE else "train"
        stem = f"own_{cls_dir.name}_{img.stem}"
        shutil.copy(img, OUT / "images" / split / f"{stem}.jpg"); shutil.copy(txt, OUT / "labels" / split / f"{stem}.txt"); own += 1
print("your photos:", own)
"""),
    code("""
# how balanced is it? weak classes need your own photos before you train
from collections import Counter
counts = Counter()
for f in (OUT / "labels" / "train").glob("*.txt"):
    for line in f.read_text().splitlines():
        counts[CLASSES[int(line.split()[0])]] += 1
for c in CLASSES:
    flag = "" if counts[c] >= 150 else "   <-- add photos"
    print(f"{c:12s} {counts[c]:5d}{flag}")
"""),
    code("""
(OUT / "dataset.yaml").write_text(yaml.safe_dump({"path": str(OUT), "train": "images/train", "val": "images/val", "names": {i: c for i, c in enumerate(CLASSES)}}))
zip_path = DEST / "reunite_dataset.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
    for p in OUT.rglob("*"):
        if p.is_file():
            z.write(p, p.relative_to(OUT))
json.dump({"classes": CLASSES, "counts": dict(counts), "sources": ["Open Images V7 (CC BY 2.0 images, CC BY 4.0 boxes)", "LVIS (if available)", "own photos"]}, open(DEST / "dataset_card.json", "w"), indent=2)
print("wrote", zip_path, zip_path.stat().st_size // 2**20, "MB")
"""),
]

# ---------------------------------------------------------------------------------------------
NB02 = [
    md("""
# 02 Fine-tune YOLO11n on the campus classes

**Compute bucket: Colab/Kaggle GPU. About 30 to 60 minutes on a T4.**

Input: `MyDrive/reunite/reunite_dataset.zip` from notebook `01`. Output: `MyDrive/reunite/detector.pt` and
`detector_metrics.json`. Copy `detector.pt` to `backend/weights/` (or run `training/export.py`): the backend loads it automatically and
skips the COCO fallback.
"""),
    code("""
!pip -q install ultralytics
"""),
    code(f"""
from google.colab import drive
drive.mount("/content/drive")
import json, zipfile
from pathlib import Path

{CLASSES}
DEST = Path("/content/drive/MyDrive/reunite")
DATA = Path("/content/dataset")
if not DATA.exists():
    with zipfile.ZipFile(DEST / "reunite_dataset.zip") as z:
        z.extractall(DATA)
print(sorted(p.name for p in DATA.iterdir()))
"""),
    code("""
from ultralytics import YOLO
model = YOLO("yolo11n.pt")            # small on purpose: it must run on an 8 GB laptop
results = model.train(
    data=str(DATA / "dataset.yaml"), epochs=60, imgsz=640, batch=32, patience=15, seed=0,
    project="/content/runs", name="reunite", device=0, workers=2, cos_lr=True, close_mosaic=10,
)
"""),
    code("""
best = YOLO("/content/runs/reunite/weights/best.pt")
metrics = best.val(data=str(DATA / "dataset.yaml"))
per_class = {CLASSES[int(c)]: float(ap) for c, ap in zip(metrics.box.ap_class_index, metrics.box.ap50)}
report = {
    "map50": float(metrics.box.map50), "map50_95": float(metrics.box.map),
    "per_class_ap50": per_class, "detector_classes": {i: c for i, c in enumerate(CLASSES)},
    "weak_classes": [c for c in CLASSES if per_class.get(c, 0) < 0.5],
}
print(json.dumps(report, indent=2))
"""),
    code("""
import shutil
shutil.copy("/content/runs/reunite/weights/best.pt", DEST / "detector.pt")
json.dump(report, open(DEST / "detector_metrics.json", "w"), indent=2)
print("saved detector.pt and detector_metrics.json to", DEST)
"""),
    md("""
Classes under 0.5 AP50 need more photos of that class (back to notebook `01`, add to `own/`). The backend's CLIP zero-shot path
still covers any class this detector is weak on, because the category head (notebook `03`) reads the whole crop, not the box.
"""),
]

# ---------------------------------------------------------------------------------------------
NB03 = [
    md("""
# 03 Attribute heads on frozen CLIP embeddings

**Compute bucket: Colab/Kaggle (a GPU makes the embedding pass quick; CPU works, just slower).**

Trains two small MLP heads on top of frozen CLIP ViT-B/32 embeddings of object crops:

* **category** (18 classes) from the labelled boxes in the dataset from notebook `01`
* **material** (optional): put a CSV at `MyDrive/reunite/material.csv` with `image,material` (plastic, metal, leather, fabric, glass, paper, wood, rubber); skipped if absent

It also measures the zero-shot baseline on the same validation crops, so the gain over "no training" is a number you can put on a slide.
Output: `heads.pt` in the exact format `backend/app/ml/vision/attributes.py` reads.
"""),
    code("""
!pip -q install open_clip_torch pillow
"""),
    code(f"""
from google.colab import drive
drive.mount("/content/drive")
import json, zipfile, random
from pathlib import Path
import numpy as np, torch, open_clip
from PIL import Image

{CLASSES}
MATERIALS = ["plastic", "metal", "leather", "fabric", "glass", "paper", "wood", "rubber"]
DEST = Path("/content/drive/MyDrive/reunite")
DATA = Path("/content/dataset")
if not DATA.exists():
    with zipfile.ZipFile(DEST / "reunite_dataset.zip") as z:
        z.extractall(DATA)
device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
model = model.to(device).eval()
tok = open_clip.get_tokenizer("ViT-B-32")
random.seed(0); torch.manual_seed(0)
"""),
    code("""
def crops(split, limit=None):
    items = []
    for lab in sorted((DATA / "labels" / split).glob("*.txt")):
        img = DATA / "images" / split / f"{lab.stem}.jpg"
        for line in lab.read_text().splitlines():
            c, x, y, w, h = line.split(); items.append((img, int(c), float(x), float(y), float(w), float(h)))
    random.shuffle(items)
    return items[:limit] if limit else items

@torch.no_grad()
def embed(items, batch=128):
    embs, ys = [], []
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]; tensors = []
        for img, c, x, y, w, h in chunk:
            im = Image.open(img).convert("RGB"); W, H = im.size
            box = (max((x - w / 2) * W, 0), max((y - h / 2) * H, 0), min((x + w / 2) * W, W), min((y + h / 2) * H, H))
            crop = im.crop(tuple(int(v) for v in box)) if box[2] - box[0] > 24 and box[3] - box[1] > 24 else im
            tensors.append(preprocess(crop))
        e = model.encode_image(torch.stack(tensors).to(device)).float()
        embs.append(torch.nn.functional.normalize(e, dim=-1).cpu()); ys += [c for _, c, *_ in chunk]
    return torch.cat(embs), torch.tensor(ys)

Xtr, ytr = embed(crops("train")); Xva, yva = embed(crops("val"))
print(Xtr.shape, Xva.shape)
"""),
    code("""
# zero-shot baseline on the same validation crops (what the backend does without heads.pt)
PHRASE = {"id_card": "student ID card", "power_bank": "power bank", "earbuds": "pair of wireless earbuds", "headphones": "pair of headphones",
          "keys": "bunch of keys", "spectacles": "pair of eyeglasses", "bottle": "water bottle", "charger": "phone charger", "notebook": "paper notebook", "watch": "wrist watch"}
TEMPLATES = ["a photo of a {}.", "a photo of a lost {}.", "a {} lying on a table.", "a close-up photo of a {}."]
with torch.no_grad():
    rows = []
    for c in CLASSES:
        p = PHRASE.get(c, c.replace("_", " "))
        e = torch.nn.functional.normalize(model.encode_text(tok([t.format(p) for t in TEMPLATES]).to(device)).float(), dim=-1).mean(0)
        rows.append(torch.nn.functional.normalize(e, dim=-1).cpu())
    T = torch.stack(rows)
zs_acc = ((100 * Xva @ T.T).argmax(1) == yva).float().mean().item()
print(f"zero-shot category accuracy: {zs_acc:.3f}")
"""),
    code("""
def train_head(Xtr, ytr, Xva, yva, n_classes, hidden=256, epochs=60, lr=1e-3, wd=1e-4):
    net = torch.nn.Sequential(torch.nn.Linear(Xtr.shape[1], hidden), torch.nn.ReLU(), torch.nn.Linear(hidden, n_classes))  # keys 0.* and 2.* (attributes.py rebuilds this)
    counts = torch.bincount(ytr, minlength=n_classes).float().clamp(min=1)
    w = (counts.sum() / counts) / n_classes                               # class-balanced loss
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    best, best_state, bad = 0.0, None, 0
    for ep in range(epochs):
        net.train(); perm = torch.randperm(len(Xtr))
        for i in range(0, len(perm), 256):
            idx = perm[i:i + 256]
            loss = torch.nn.functional.cross_entropy(net(Xtr[idx]), ytr[idx], weight=w, label_smoothing=0.05)
            opt.zero_grad(); loss.backward(); opt.step()
        net.eval()
        with torch.no_grad():
            acc = (net(Xva).argmax(1) == yva).float().mean().item()
        if acc > best: best, best_state, bad = acc, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 10: break
    net.load_state_dict(best_state)
    return net, best

cat_net, cat_acc = train_head(Xtr, ytr, Xva, yva, len(CLASSES))
print(f"trained category head accuracy: {cat_acc:.3f}  (zero-shot {zs_acc:.3f})")
"""),
    code("""
# optional material head from a CSV of weak labels
mat_blob, mat_acc = None, None
csv_path = DEST / "material.csv"
if csv_path.exists():
    import csv
    rows = [r for r in csv.DictReader(open(csv_path)) if r["material"] in MATERIALS]
    random.shuffle(rows)
    embs, ys = [], []
    with torch.no_grad():
        for r in rows:
            e = model.encode_image(preprocess(Image.open(r["image"]).convert("RGB")).unsqueeze(0).to(device)).float()
            embs.append(torch.nn.functional.normalize(e, dim=-1).cpu()[0]); ys.append(MATERIALS.index(r["material"]))
    X, y = torch.stack(embs), torch.tensor(ys); cut = int(len(X) * 0.85)
    mat_net, mat_acc = train_head(X[:cut], y[:cut], X[cut:], y[cut:], len(MATERIALS), hidden=128)
    mat_blob = {"in_dim": 512, "hidden": 128, "classes": MATERIALS, "state_dict": {k: v.cpu() for k, v in mat_net.state_dict().items()}}
    print(f"material head accuracy: {mat_acc:.3f}")
else:
    print("no material.csv: material stays zero-shot")
"""),
    code("""
blob = {"category": {"in_dim": 512, "hidden": 256, "classes": CLASSES, "state_dict": {k: v.cpu() for k, v in cat_net.state_dict().items()}}}
if mat_blob: blob["material"] = mat_blob
torch.save(blob, DEST / "heads.pt")
json.dump({"category_accuracy": cat_acc, "zero_shot_category_accuracy": zs_acc, "material_accuracy": mat_acc, "n_train": len(Xtr), "n_val": len(Xva), "classes": CLASSES},
          open(DEST / "heads_metrics.json", "w"), indent=2)
print("saved heads.pt and heads_metrics.json to", DEST)
"""),
]

# ---------------------------------------------------------------------------------------------
NB04 = [
    md("""
# 04 (stretch) Metric learning: a small image adapter for instance matching

**Compute bucket, optional. Needs REAL lost/found pairs in `eval/pairs/manifest.csv` with photos on both sides (50+ pairs; 150+ is better).**

CLIP tells a laptop from a phone well, but it is weaker at "this exact laptop versus another black laptop". This notebook trains a
**residual adapter** on top of frozen CLIP image embeddings with a triplet loss over your pairs:

    image = normalize(x + x @ delta)

Only image embeddings are adapted, so text and text-to-photo similarity keep CLIP's geometry. Output `projection.pt` is picked up by
`backend/app/ml/vision/embedder.py` when it sits in `backend/weights/`. Always rerun `python -m eval.run_eval --pairs real` afterwards
and keep it only if P@1 improves on the held-out pairs.
"""),
    code("""
!pip -q install open_clip_torch pillow
"""),
    code("""
from google.colab import drive
drive.mount("/content/drive")
import csv, json, random
from pathlib import Path
import numpy as np, torch, open_clip
from PIL import Image

PAIRS = Path("/content/drive/MyDrive/reunite/pairs")     # copy eval/pairs here: manifest.csv plus the images it points to
DEST = Path("/content/drive/MyDrive/reunite")
device = "cuda" if torch.cuda.is_available() else "cpu"
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
model = model.to(device).eval()
random.seed(0); torch.manual_seed(0)

rows = list(csv.DictReader(open(PAIRS / "manifest.csv")))
by = {}
for r in rows:
    if r["image"]:
        by.setdefault(r["pair_id"], {})[r["side"]] = PAIRS / r["image"]
pairs = {p: s for p, s in by.items() if "lost" in s and "found" in s}
print(len(pairs), "pairs with a photo on both sides")
assert len(pairs) >= 50, "collect more pairs first (see eval/README.md)"
"""),
    code("""
@torch.no_grad()
def emb(path):
    e = model.encode_image(preprocess(Image.open(path).convert("RGB")).unsqueeze(0).to(device)).float()
    return torch.nn.functional.normalize(e, dim=-1).cpu()[0]

ids = sorted(pairs); random.shuffle(ids)
cut = int(len(ids) * 0.7); train_ids, val_ids = ids[:cut], ids[cut:]      # split by pair id, never by image
E = {p: (emb(pairs[p]["lost"]), emb(pairs[p]["found"])) for p in ids}

def p_at_1(delta, which):
    L = torch.stack([E[p][0] for p in which]); Fd = torch.stack([E[p][1] for p in which])
    adapt = lambda x: torch.nn.functional.normalize(x + x @ delta, dim=-1)
    sims = adapt(L) @ adapt(Fd).T
    return (sims.argmax(1) == torch.arange(len(which))).float().mean().item()

zero = torch.zeros(512, 512)
print("held-out image-only P@1 before:", round(p_at_1(zero, val_ids), 3))
"""),
    code("""
delta = torch.nn.Parameter(torch.zeros(512, 512))
opt = torch.optim.AdamW([delta], lr=5e-4, weight_decay=0.0)
margin, reg = 0.2, 1e-2
L = torch.stack([E[p][0] for p in train_ids]); Fd = torch.stack([E[p][1] for p in train_ids])
adapt = lambda x: torch.nn.functional.normalize(x + x @ delta, dim=-1)
best, best_delta = p_at_1(zero, val_ids), zero.clone()
for step in range(600):
    a, p = adapt(L), adapt(Fd)
    sims = a @ p.T
    pos = sims.diag().unsqueeze(1)
    neg_mask = ~torch.eye(len(L), dtype=torch.bool)
    loss = torch.relu(margin + sims - pos)[neg_mask].mean() + reg * delta.pow(2).sum()      # triplet loss with all in-batch negatives
    opt.zero_grad(); loss.backward(); opt.step()
    if step % 20 == 0:
        with torch.no_grad():
            acc = p_at_1(delta.detach(), val_ids)
        if acc > best: best, best_delta = acc, delta.detach().clone()
print("held-out image-only P@1 after:", round(best, 3))
"""),
    code("""
torch.save({"delta": best_delta.cpu(), "note": "residual adapter: image = normalize(x + x @ delta)"}, DEST / "projection.pt")
json.dump({"heldout_image_p_at_1_before": p_at_1(zero, val_ids), "heldout_image_p_at_1_after": best, "n_train_pairs": len(train_ids), "n_val_pairs": len(val_ids)},
          open(DEST / "projection_metrics.json", "w"), indent=2)
print("saved projection.pt")
"""),
    md("""
Copy `projection.pt` to `backend/weights/`, restart the backend, then **rerun the real-pair eval**. If P@1 does not improve on held-out
pairs, delete the file: the adapter is only worth keeping when it earns its place.
"""),
]

NOTEBOOKS = {
    "01_build_dataset.ipynb": NB01,
    "02_finetune_yolo.ipynb": NB02,
    "03_attribute_heads.ipynb": NB03,
    "04_metric_learning.ipynb": NB04,
}

if __name__ == "__main__":
    for name, cells in NOTEBOOKS.items():
        nb = notebook(cells)
        check(name, nb)
        (HERE / name).write_text(json.dumps(nb, indent=1))
        print("wrote", name, f"({len(cells)} cells)")
