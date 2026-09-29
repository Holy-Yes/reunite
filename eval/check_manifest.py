"""Validate a pairs manifest before you spend minutes evaluating it.

    python -m eval.check_manifest                      # eval/pairs/manifest.csv (your real pairs)
    python -m eval.check_manifest eval/pairs/synthetic/manifest.csv
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import taxonomy  # noqa: E402

REQUIRED = ["pair_id", "side", "image", "text", "zone", "timestamp"]


def _ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    return d


def check(path: Path) -> tuple[list[str], list[str]]:
    """(errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return [f"{path} does not exist"], []
    zones = set(taxonomy.zone_aliases())
    cats = set(taxonomy.category_names())
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            return [f"missing columns: {missing}"], []
        rows = list(reader)
    if not rows:
        return [], ["the manifest has no rows yet"]
    by: dict[str, dict[str, dict]] = {}
    for n, r in enumerate(rows, start=2):
        where = f"row {n} ({r['pair_id']}/{r['side']})"
        if r["side"] not in ("lost", "found"):
            errors.append(f"{where}: side must be lost or found")
            continue
        if r["side"] in by.setdefault(r["pair_id"], {}):
            errors.append(f"{where}: duplicate {r['side']} row for this pair")
        by[r["pair_id"]][r["side"]] = r
        if not (r["image"] or r["text"].strip()):
            errors.append(f"{where}: needs a photo or a description")
        if r["image"] and not (path.parent / r["image"]).exists():
            errors.append(f"{where}: image {r['image']} not found next to the manifest")
        if r["zone"] not in zones:
            errors.append(f"{where}: unknown zone '{r['zone']}' (known: {', '.join(sorted(zones))})")
        cat = (r.get("category") or "").strip()
        if cat and cat not in cats:
            errors.append(f"{where}: unknown category '{cat}'")
        try:
            if "/" in r["timestamp"]:
                a, b = (_ts(x) for x in r["timestamp"].split("/", 1))
                if b < a:
                    errors.append(f"{where}: the window ends before it starts")
                if r["side"] == "found":
                    warnings.append(f"{where}: a found row should carry one moment, not a window")
            else:
                _ts(r["timestamp"])
                if r["side"] == "lost":
                    warnings.append(f"{where}: a lost row is better with a window 'start/end'")
        except ValueError:
            errors.append(f"{where}: timestamp is not ISO 8601")
    for pid, sides in by.items():
        if set(sides) != {"lost", "found"}:
            errors.append(f"pair {pid}: needs exactly one lost and one found row (has {sorted(sides)})")
            continue
        try:
            lost_start = _ts(sides["lost"]["timestamp"].split("/")[0])
            found_at = _ts(sides["found"]["timestamp"].split("/")[0])
            if found_at < lost_start:
                errors.append(f"pair {pid}: found before the lost window starts. The matcher ignores those pairs, so it cannot be a true match")
        except ValueError:
            pass
    n_pairs = len(by)
    both = sum(1 for s in by.values() if s.get("lost", {}).get("image") and s.get("found", {}).get("image"))
    text_only = sum(1 for s in by.values() if s.get("lost", {}).get("text") and not s.get("lost", {}).get("image"))
    warnings.append(f"{n_pairs} pairs; {both} with photos on both sides; {text_only} with a text-only lost report")
    if n_pairs < 150:
        warnings.append("aim for 150 to 300 pairs; fewer makes P@1 noisy (each pair moves it by 1/n)")
    return errors, warnings


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "eval" / "pairs" / "manifest.csv"
    errors, warnings = check(path)
    for w in warnings:
        print("note:", w)
    for e in errors:
        print("ERROR:", e)
    print("OK" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
