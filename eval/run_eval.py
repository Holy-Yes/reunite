"""Evaluate the matcher end to end, with no database.

    python -m eval.run_eval --pairs synthetic            # generated pairs (optimistic)
    python -m eval.run_eval --pairs real                 # eval/pairs/manifest.csv (your own photographed pairs)
    python -m eval.run_eval --pairs both --seed 1 --pool-size 50

For every lost report it takes the whole found pool, generates candidates, scores them, and ranks them,
using the same extraction and matching code the API runs. Then it reports:

  * P@1, P@5, P@10   success@k: the true match is in the top k (there is exactly one true match per lost report)
  * Recall@k         stage-1 candidate generation: is the true match in the top k by embedding similarity alone?
  * MRR and mAP      (identical when each query has one relevant item)
  * ECE + reliability diagram, on a held-out 30% of pair ids, after fitting a logistic calibration on 70%
  * per-category breakdown, and an ablation over feature groups

Reports go to eval/reports/<run_id>.json (shape in docs/WEBSITE_PROMPT.md section 6) and .md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pickle
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("JWT_SECRET", "eval-only")

from PIL import Image  # noqa: E402

from app import taxonomy  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.ml import pipeline, registry  # noqa: E402
from app.ml.matching import calibrate, candidates, features as F, scorer  # noqa: E402

EVAL = ROOT / "eval"
REPORTS = EVAL / "reports"
CACHE = ROOT / ".cache" / "eval"
TARGETS = {"p_at_1": 0.60, "p_at_5": 0.85}
CACHE_VERSION = "v2"

ABLATION = [
    ("image only", {"image"}),
    ("text only", {"text"}),
    ("+ attributes", {"image", "text", "category", "color", "brand", "marks"}),
    ("+ text-to-photo", {"image", "text", "category", "color", "brand", "marks", "cross_modal"}),
    ("+ location and time", set(F.FEATURES)),
]


@dataclass
class Row:
    pair_id: str
    side: str
    image: str
    text: str
    zone: str
    timestamp: str
    category: str
    source: str


# ---- loading and extraction --------------------------------------------------------------


def load_manifest(path: Path, source: str) -> list[Row]:
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("pair_id"):
                continue
            rows.append(Row(r["pair_id"], r["side"], (r.get("image") or "").strip(), (r.get("text") or "").strip(), r["zone"], r["timestamp"], (r.get("category") or "").strip(), source))
    return rows


def _parse_ts(ts: str) -> tuple[datetime, datetime]:
    """A lost row carries "start/end"; a found row carries one moment."""
    def one(s: str) -> datetime:
        d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    if "/" in ts:
        a, b = ts.split("/", 1)
        return one(a), one(b)
    t = one(ts)
    return t, t


def _cache_key(row: Row, base: Path) -> str:
    h = hashlib.sha1()
    h.update(f"{CACHE_VERSION}|{get_settings().ml_mode}|{row.text}|".encode())
    if row.image:
        h.update((base / row.image).read_bytes())
    return h.hexdigest()


def extract_row(row: Row, base: Path) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{_cache_key(row, base)}.pkl"
    if f.exists():
        return pickle.loads(f.read_bytes())
    images = [Image.open(base / row.image).convert("RGB")] if row.image else []
    ex = pipeline.extract(row.text or None, images)
    out = {
        "attributes": ex.attributes,
        "image_embs": [r.embedding for r in ex.images if r.embedding is not None],
        "text_emb": ex.text_embedding,
        "clip_text_emb": ex.clip_text_embedding,
    }
    f.write_bytes(pickle.dumps(out))
    return out


def build_view(row: Row, ex: dict) -> F.ItemView:
    a = ex["attributes"]
    cat = a.get("category") or {}
    start, end = _parse_ts(row.timestamp)
    return F.ItemView(
        id=f"{row.pair_id}:{row.side}", kind=row.side, zone_id=row.zone, occurred_from=start, occurred_to=end,
        category=cat.get("value"), category_conf=float(cat.get("confidence", 0.0)), category_dist=F.dist_from_attr(cat),
        colors=[c["value"] for c in a.get("colors", [])], brand=(a.get("brand") or {}).get("value"),
        marks=[m["value"] for m in a.get("marks", [])], image_embs=ex["image_embs"], text_emb=ex["text_emb"], clip_text_emb=ex["clip_text_emb"],
    )


# ---- ranking -------------------------------------------------------------------------------


@dataclass
class Query:
    pair_id: str
    category: str
    source: str
    candidates: list[str]           # candidate found pair ids in scoring order
    stage1_rank: int | None         # rank of the true match in candidate generation (1-based), None if absent
    feats: dict[str, list[F.Feature]]


def run_queries(lost: dict[str, F.ItemView], found: dict[str, F.ItemView], cats: dict[str, str], sources: dict[str, str], pool_size: int) -> list[Query]:
    pool = list(found.values())
    k = pool_size or len(pool)
    out: list[Query] = []
    for pid, lv in lost.items():
        ranked = candidates.top_candidates(lv, pool, k)
        ids = [c.id.split(":")[0] for c in ranked]
        feats: dict[str, list[F.Feature]] = {}
        for c in ranked:
            f = F.compute_features(lv, c)
            if f is not None:
                feats[c.id.split(":")[0]] = f
        out.append(Query(pid, cats.get(pid, ""), sources.get(pid, ""), ids, ids.index(pid) + 1 if pid in ids else None, feats))
    return out


def rank_of_truth(q: Query, score_fn) -> int | None:  # noqa: ANN001
    scored = sorted(((score_fn(f), cid) for cid, f in q.feats.items()), key=lambda t: (-t[0], t[1]))
    for i, (_, cid) in enumerate(scored, start=1):
        if cid == q.pair_id:
            return i
    return None


def _hand(feats: list[F.Feature]) -> float:
    return scorer.score_pair(feats, calibration=None).score


def ranking_metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    hit = lambda k: sum(1 for r in ranks if r is not None and r <= k) / n if n else 0.0  # noqa: E731
    mrr = sum(1.0 / r for r in ranks if r) / n if n else 0.0
    return {"p_at_1": hit(1), "p_at_5": hit(5), "p_at_10": hit(10), "mrr": mrr, "map": mrr, "n": n}


def masked(feats: list[F.Feature], keep: set[str]) -> list[F.Feature]:
    return [f if f.key in keep else F.Feature(f.key, f.value, False, f.detail, "ablated") for f in feats]


# ---- calibration ---------------------------------------------------------------------------


def calibration_data(queries: list[Query], negatives: int = 15) -> tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for q in queries:
        scored = sorted(((_hand(f), cid, f) for cid, f in q.feats.items()), key=lambda t: -t[0])
        negs = [t for t in scored if t[1] != q.pair_id][:negatives]           # hard negatives: the top-ranked wrong answers
        for _, cid, f in [t for t in scored if t[1] == q.pair_id] + negs:
            X.append(scorer.feature_vector(f))
            y.append(1 if cid == q.pair_id else 0)
    return np.array(X), np.array(y)


def split_ids(ids: list[str], seed: int, train_share: float = 0.7) -> tuple[set[str], set[str]]:
    ids = sorted(set(ids))
    random.Random(seed).shuffle(ids)
    cut = int(len(ids) * train_share)
    return set(ids[:cut]), set(ids[cut:])


# ---- report --------------------------------------------------------------------------------


def evaluate(rows: list[Row], base_of: dict[str, Path], seed: int, pool_size: int, calibrate_on: bool, limit: int | None) -> dict:
    lost_rows = [r for r in rows if r.side == "lost"]
    found_rows = [r for r in rows if r.side == "found"]
    if limit:
        keep = {r.pair_id for r in lost_rows[:limit]}
        lost_rows = [r for r in lost_rows if r.pair_id in keep]
        found_rows = [r for r in found_rows if r.pair_id in keep]
    t0 = time.time()
    lost, found, cats, sources = {}, {}, {}, {}
    for i, r in enumerate(lost_rows + found_rows, start=1):
        v = build_view(r, extract_row(r, base_of[r.source]))
        (lost if r.side == "lost" else found)[r.pair_id] = v
        if i % 20 == 0:
            print(f"  extracted {i}/{len(lost_rows) + len(found_rows)}  ({time.time() - t0:.0f}s)", flush=True)
    for r in lost_rows:
        cats[r.pair_id] = r.category or (lost[r.pair_id].category or "unknown")
        sources[r.pair_id] = r.source

    queries = run_queries(lost, found, cats, sources, pool_size)
    n = len(queries)

    # headline: the hand-weighted scorer that ships by default
    ranks = [rank_of_truth(q, _hand) for q in queries]
    metrics = ranking_metrics(ranks)
    metrics.update(
        p_at_1=round(metrics["p_at_1"], 4), p_at_5=round(metrics["p_at_5"], 4), p_at_10=round(metrics["p_at_10"], 4),
        mrr=round(metrics["mrr"], 4), map=round(metrics["map"], 4),
        recall_at_5=round(sum(1 for q in queries if q.stage1_rank and q.stage1_rank <= 5) / n, 4) if n else 0.0,
        recall_at_10=round(sum(1 for q in queries if q.stage1_rank and q.stage1_rank <= 10) / n, 4) if n else 0.0,
        candidate_recall=round(sum(1 for q in queries if q.stage1_rank) / n, 4) if n else 0.0,
    )

    # calibration: fit on 70% of pair ids, measure on the held-out 30%
    reliability: list[dict] = []
    cal_block: dict = {"fitted": False}
    blob = None
    if calibrate_on and n >= 10:
        train_ids, test_ids = split_ids([q.pair_id for q in queries], seed)
        train_q = [q for q in queries if q.pair_id in train_ids]
        test_q = [q for q in queries if q.pair_id in test_ids]
        Xtr, ytr = calibration_data(train_q)
        if ytr.sum() >= 3 and (ytr == 0).sum() >= 3:
            blob = calibrate.fit(Xtr, ytr, seed=seed)
            probs, labels, hand_probs = [], [], []
            for q in test_q:
                for cid, f in q.feats.items():
                    probs.append(float(calibrate.predict(blob, np.array([scorer.feature_vector(f)]))[0]))
                    hand_probs.append(_hand(f))
                    labels.append(1 if cid == q.pair_id else 0)
            probs_a, labels_a, hand_a = np.array(probs), np.array(labels), np.array(hand_probs)
            cal_ranks = [rank_of_truth(q, lambda f: float(calibrate.predict(blob, np.array([scorer.feature_vector(f)]))[0])) for q in test_q]
            reliability = calibrate.reliability(probs_a, labels_a)
            metrics["ece"] = round(calibrate.ece(probs_a, labels_a), 4)
            metrics["ece_uncalibrated"] = round(calibrate.ece(hand_a, labels_a), 4)
            cal_block = {
                "fitted": True, "model_version": blob["model_version"], "n_train_pairs": len(train_q), "n_heldout_pairs": len(test_q),
                "heldout_metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in ranking_metrics(cal_ranks).items()},
                "heldout_metrics_hand_scorer": {k: round(v, 4) if isinstance(v, float) else v for k, v in ranking_metrics([rank_of_truth(q, _hand) for q in test_q]).items()},
            }
    if "ece" not in metrics:
        metrics["ece"] = None

    per_cat: dict[str, list[int | None]] = defaultdict(list)
    for q, r in zip(queries, ranks):
        per_cat[q.category or "unknown"].append(r)
    per_category = [
        {"category": c, "p_at_1": round(ranking_metrics(rs)["p_at_1"], 4), "p_at_5": round(ranking_metrics(rs)["p_at_5"], 4), "n": len(rs)}
        for c, rs in sorted(per_cat.items())
    ]

    ablation = []
    for name, keep in ABLATION:
        rs = [rank_of_truth(q, lambda f, keep=keep: scorer.score_pair(masked(f, keep), calibration=None).score) for q in queries]
        m = ranking_metrics(rs)
        ablation.append({"name": name, "p_at_1": round(m["p_at_1"], 4), "p_at_5": round(m["p_at_5"], 4)})

    return {
        "n_pairs": n, "metrics": metrics, "reliability": reliability, "per_category": per_category, "ablation": ablation,
        "calibration": cal_block, "_blob": blob, "seconds": round(time.time() - t0, 1),
    }


def write_reports(kind: str, result: dict, seed: int, pool_size: int) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    run_id = f"{today}-{kind}"
    m = result["metrics"]
    body = {
        "run_id": run_id, "pairs": kind, "n_pairs": result["n_pairs"], "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {k: m[k] for k in ("p_at_1", "p_at_5", "p_at_10", "recall_at_5", "mrr", "map", "ece") if k in m},
        "targets": TARGETS,
        "reliability": result["reliability"], "per_category": result["per_category"], "ablation": result["ablation"],
        "extra": {
            "recall_at_10": m.get("recall_at_10"), "candidate_recall": m.get("candidate_recall"), "ece_uncalibrated": m.get("ece_uncalibrated"),
            "calibration": result["calibration"], "seed": seed, "pool_size": pool_size or "all", "ml_mode": get_settings().ml_mode,
            "scorer": scorer.HAND_VERSION, "stages": registry.status(), "seconds": result["seconds"],
            "notes": (
                "Synthetic pairs are OPTIMISTIC: both views come from one public photo and the text is generated from the same labels. "
                "Do not present these numbers as real-world performance." if kind == "synthetic" else "Real pairs: photographed lost/found views of the same object."
            ),
        },
    }
    (REPORTS / f"{run_id}.json").write_text(json.dumps(body, indent=2, default=float))
    (REPORTS / f"{run_id}.md").write_text(markdown(body))
    if result.get("_blob"):
        calibrate.save(result["_blob"], REPORTS / f"{run_id}.calibration.json")
    return REPORTS / f"{run_id}.json"


def markdown(r: dict) -> str:
    m, t = r["metrics"], r["targets"]
    badge = "SYNTHETIC pairs (optimistic)" if r["pairs"] == "synthetic" else "REAL pairs"
    ok = lambda v, tgt: "meets target" if v >= tgt else "below target"  # noqa: E731
    lines = [
        f"# Eval report {r['run_id']}", "", f"**Pair set: {badge}.** {r['n_pairs']} lost reports, each ranked against the whole found pool.", "",
        "## Headline", "", "| Metric | Value | Target |", "|---|---|---|",
        f"| Precision@1 | {m['p_at_1']:.3f} | {t['p_at_1']} ({ok(m['p_at_1'], t['p_at_1'])}) |",
        f"| Precision@5 | {m['p_at_5']:.3f} | {t['p_at_5']} ({ok(m['p_at_5'], t['p_at_5'])}) |",
        f"| Precision@10 | {m['p_at_10']:.3f} | |", f"| Recall@5 (candidate generation) | {m['recall_at_5']:.3f} | |",
        f"| MRR | {m['mrr']:.3f} | |", f"| mAP | {m['map']:.3f} | (equals MRR: one true match per query) |",
        f"| ECE (calibrated, held-out 30%) | {m['ece'] if m.get('ece') is not None else 'n/a'} | lower is better |", "",
    ]
    if r["extra"].get("ece_uncalibrated") is not None:
        lines += [f"Uncalibrated (hand-set weights read as probabilities) ECE on the same held-out pairs: {r['extra']['ece_uncalibrated']}.", ""]
    lines += ["## Ablation (which evidence carries the ranking)", "", "| Feature set | P@1 | P@5 |", "|---|---|---|"]
    lines += [f"| {a['name']} | {a['p_at_1']:.3f} | {a['p_at_5']:.3f} |" for a in r["ablation"]]
    lines += ["", "## Per category", "", "| Category | P@1 | P@5 | n |", "|---|---|---|---|"]
    lines += [f"| {c['category']} | {c['p_at_1']:.2f} | {c['p_at_5']:.2f} | {c['n']} |" for c in r["per_category"]]
    if r["reliability"]:
        lines += ["", "## Reliability (10 bins, held-out)", "", "| Bin | Confidence | Accuracy | n |", "|---|---|---|---|"]
        lines += [f"| {b['bin']} | {b['confidence']:.2f} | {b['accuracy']:.2f} | {b['n']} |" for b in r["reliability"]]
    lines += ["", "## Notes", "", r["extra"]["notes"], "", f"Stages: `{json.dumps(r['extra']['stages'])}`", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", choices=["synthetic", "real", "both"], default="synthetic")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--pool-size", type=int, default=0, help="candidates per query after candidate generation (0 = all found rows)")
    ap.add_argument("--no-calibrate", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="only the first N pairs (debugging)")
    ap.add_argument("--write-weights", action="store_true", help="copy the fitted calibration to backend/weights/calibration.json (use real pairs, not synthetic)")
    args = ap.parse_args()

    kinds = ["synthetic", "real"] if args.pairs == "both" else [args.pairs]
    for kind in kinds:
        path = EVAL / "pairs" / ("synthetic/manifest.csv" if kind == "synthetic" else "manifest.csv")
        if not path.exists():
            print(f"no manifest at {path}" + ("  (run: python -m eval.synthetic_pairs)" if kind == "synthetic" else "  (see eval/README.md)"))
            continue
        rows = load_manifest(path, kind)
        if not rows:
            print(f"{path} has no rows yet")
            continue
        base = {kind: path.parent}          # image paths in a manifest are relative to the manifest
        print(f"[{kind}] {len(rows) // 2} pairs, ML_MODE={get_settings().ml_mode}", flush=True)
        result = evaluate(rows, base, args.seed, args.pool_size, not args.no_calibrate, args.limit)
        out = write_reports(kind, result, args.seed, args.pool_size)
        m = result["metrics"]
        print(f"[{kind}] P@1={m['p_at_1']:.3f} P@5={m['p_at_5']:.3f} P@10={m['p_at_10']:.3f} MRR={m['mrr']:.3f} ECE={m.get('ece')}  -> {out}")
        if args.write_weights and result.get("_blob"):
            dest = ROOT / "backend" / "weights" / "calibration.json"
            calibrate.save(result["_blob"], dest)
            print("wrote", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
