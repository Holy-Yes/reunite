#!/usr/bin/env python3
"""Fetch building footprints around the VNR VJIET campus from OpenStreetMap and write them as a small JSON file
that the campus map extrudes into a 3D view. No API key. Data (c) OpenStreetMap contributors, ODbL.

    python3 scripts/build_campus_buildings.py

Output: frontend/src/campus/buildings.json  ->  [{"id", "name"?, "h", "r": [lon, lat, lon, lat, ...]}]
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

BBOX = (17.5350, 78.3825, 17.5430, 78.3885)  # south, west, north, east
OUT = Path(__file__).resolve().parent.parent / "frontend/src/campus/buildings.json"
URL = "https://overpass-api.de/api/interpreter"


def fetch() -> list[dict]:
    s, w, n, e = BBOX
    query = f'[out:json][timeout:60];way["building"]({s},{w},{n},{e});out geom tags;'
    # curl rather than urllib: python.org builds on macOS often lack a CA bundle.
    res = subprocess.run(
        ["curl", "-sf", "-m", "90", "-A", "reunite-campus-map/0.1 (student project)", "-H", "Accept: application/json",
         "--data-urlencode", f"data={query}", URL],
        capture_output=True, text=True, check=True,
    )
    return json.loads(res.stdout)["elements"]


def area_m2(ring: list[dict]) -> float:
    k = math.cos(math.radians(ring[0]["lat"]))
    pts = [(p["lon"] * 111320 * k, p["lat"] * 110540) for p in ring]
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2


def height(tags: dict, area: float) -> float:
    if "height" in tags:
        try:
            return float(str(tags["height"]).split()[0])
        except ValueError:
            pass
    if "building:levels" in tags:
        try:
            return float(tags["building:levels"]) * 3.4
        except ValueError:
            pass
    if tags.get("building") == "roof":
        return 4.0
    # Most footprints carry no height. Size is a fair guess: big blocks are academic buildings of ~4 floors.
    return 18.0 if area > 1500 else 14.0 if area > 600 else 10.0 if area > 200 else 6.0


def main() -> None:
    out = []
    for el in fetch():
        ring = el.get("geometry") or []
        if len(ring) < 4:
            continue
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        tags = el.get("tags", {})
        item = {"id": el["id"], "h": round(height(tags, area_m2(ring)), 1), "r": [c for p in ring for c in (round(p["lon"], 6), round(p["lat"], 6))]}
        if tags.get("name"):
            item["name"] = tags["name"]
        out.append(item)
    out.sort(key=lambda b: b["id"])
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(out)} buildings -> {OUT.relative_to(OUT.parents[3])} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
