#!/usr/bin/env python
"""Validate trained weights and install them where the backend loads them from.

    python training/export.py \\
        --detector runs/reunite/weights/best.pt --detector-metrics detector_metrics.json \\
        --heads heads.pt --heads-metrics heads_metrics.json \\
        [--projection projection.pt] [--calibration calibration.json] [--dataset-card dataset_card.json]

Writes into backend/weights/ (override with --weights-dir): detector.pt, heads.pt, projection.pt,
calibration.json, and model_card.json (class list, metrics, data sources, date). The backend hot-loads whatever is
present at startup and logs which path each stage took; `GET /admin/eval/reports/{run}` shows the model card.

Nothing is copied unless every file passes its check, so a bad export cannot leave the backend half-updated.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


class ExportError(Exception):
    pass


def check_heads(path: Path) -> dict:
    """heads.pt: {"category": {in_dim, hidden, classes, state_dict}, "material"?: {...}} matching attributes.py."""
    import torch

    from app import taxonomy

    blob = torch.load(path, map_location="cpu")
    if "category" not in blob:
        raise ExportError("heads.pt has no 'category' head")
    for name, spec in blob.items():
        for key in ("in_dim", "hidden", "classes", "state_dict"):
            if key not in spec:
                raise ExportError(f"heads.pt[{name}] is missing '{key}'")
        net = torch.nn.Sequential(torch.nn.Linear(spec["in_dim"], spec["hidden"]), torch.nn.ReLU(), torch.nn.Linear(spec["hidden"], len(spec["classes"])))
        try:
            net.load_state_dict(spec["state_dict"])
        except RuntimeError as e:
            raise ExportError(f"heads.pt[{name}] state_dict does not fit a 2-layer MLP: {e}") from e
        if spec["in_dim"] != 512:
            raise ExportError(f"heads.pt[{name}] expects {spec['in_dim']}-d embeddings; CLIP ViT-B/32 gives 512")
        net(torch.zeros(1, spec["in_dim"]))
    cats, want = list(blob["category"]["classes"]), taxonomy.category_names()
    if set(cats) != set(want):
        raise ExportError(f"category classes differ from the taxonomy: missing {sorted(set(want) - set(cats))}, unknown {sorted(set(cats) - set(want))}")
    if "material" in blob and set(blob["material"]["classes"]) != set(taxonomy.materials()):
        raise ExportError("material classes differ from the taxonomy")
    return {"classes": cats, "materials": "material" in blob}


def check_detector(path: Path, metrics: dict | None, load: bool) -> dict:
    from app import taxonomy

    names: dict | list | None = (metrics or {}).get("detector_classes")
    if load:
        from ultralytics import YOLO

        model = YOLO(str(path))
        names = {int(k): v for k, v in model.names.items()}
    if not names:
        raise ExportError("cannot read the detector's class names: pass --detector-metrics (from notebook 02) or drop --skip-load")
    labels = list(names.values()) if isinstance(names, dict) else list(names)
    unknown = sorted(set(labels) - set(taxonomy.category_names()))
    if unknown:
        raise ExportError(f"detector classes not in the taxonomy: {unknown}")
    return {"detector_classes": {int(k): v for k, v in names.items()} if isinstance(names, dict) else dict(enumerate(names))}


def check_projection(path: Path) -> None:
    import torch

    blob = torch.load(path, map_location="cpu")
    d = blob.get("delta")
    if d is None or tuple(d.shape) != (512, 512):
        raise ExportError("projection.pt needs a 512 x 512 'delta'")


def check_calibration(path: Path) -> None:
    from app.ml.matching.features import FEATURES
    from app.ml.matching.scorer import MASK_TERMS

    blob = json.loads(path.read_text())
    if blob.get("features") != FEATURES or len(blob.get("coef", [])) != len(FEATURES) + len(MASK_TERMS) or "intercept" not in blob:
        raise ExportError("calibration.json does not match the current feature list (refit it with `python -m eval.run_eval`)")


def export(args: argparse.Namespace) -> Path:
    weights = Path(args.weights_dir)
    card: dict = {"created_at": datetime.now(timezone.utc).isoformat(), "stages": {}}
    plan: list[tuple[Path, str]] = []

    metrics = json.loads(Path(args.detector_metrics).read_text()) if args.detector_metrics else None
    if args.detector:
        info = check_detector(Path(args.detector), metrics, not args.skip_load)
        card.update(info)
        card["detector_metrics"] = {k: v for k, v in (metrics or {}).items() if k != "detector_classes"}
        card["stages"]["detector"] = "fine-tuned YOLO11n"
        plan.append((Path(args.detector), "detector.pt"))
    if args.heads:
        info = check_heads(Path(args.heads))
        card["head_classes"] = info["classes"]
        card["heads_metrics"] = json.loads(Path(args.heads_metrics).read_text()) if args.heads_metrics else None
        card["stages"]["attribute_heads"] = "MLP heads on frozen CLIP" + (" (category + material)" if info["materials"] else " (category)")
        plan.append((Path(args.heads), "heads.pt"))
    if args.projection:
        check_projection(Path(args.projection))
        card["stages"]["projection"] = "image adapter (metric learning)"
        plan.append((Path(args.projection), "projection.pt"))
    if args.calibration:
        check_calibration(Path(args.calibration))
        card["stages"]["scorer"] = "logistic calibration"
        card["calibration_version"] = json.loads(Path(args.calibration).read_text()).get("model_version")
        plan.append((Path(args.calibration), "calibration.json"))
    if not plan:
        raise ExportError("nothing to export: pass at least one of --detector --heads --projection --calibration")
    if args.dataset_card:
        card["data_sources"] = json.loads(Path(args.dataset_card).read_text())

    weights.mkdir(parents=True, exist_ok=True)
    for src, name in plan:                       # every check passed: now copy
        shutil.copy(src, weights / name)
    existing = json.loads((weights / "model_card.json").read_text()) if (weights / "model_card.json").exists() else {}
    existing.update({k: v for k, v in card.items() if k != "stages"})
    existing["stages"] = {**existing.get("stages", {}), **card["stages"]}
    (weights / "model_card.json").write_text(json.dumps(existing, indent=2))
    return weights / "model_card.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("detector", "detector-metrics", "heads", "heads-metrics", "projection", "calibration", "dataset-card"):
        ap.add_argument(f"--{name}")
    ap.add_argument("--weights-dir", default=str(ROOT / "backend" / "weights"))
    ap.add_argument("--skip-load", action="store_true", help="do not open the detector with ultralytics (use its metrics file for class names)")
    args = ap.parse_args(argv)
    try:
        card = export(args)
    except ExportError as e:
        print(f"export refused: {e}", file=sys.stderr)
        return 2
    print("installed. model card:", card)
    print("restart the backend, then rerun:  python -m eval.run_eval --pairs real")
    return 0


if __name__ == "__main__":
    sys.exit(main())
