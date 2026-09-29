#!/usr/bin/env python
"""Build campus zone config.

    python scripts/build_campus_zones.py --vnrvjiet                                   # real VNR VJIET spots
    python scripts/build_campus_zones.py --placeholder
    python scripts/build_campus_zones.py --bbox 17.44,78.34,17.46,78.36        # south,west,north,east (OSM Overpass)
    python scripts/build_campus_zones.py --elements path/to/overpass.json        # offline, from a saved response

Writes config/campus/zones.geojson, config/campus/zone_graph.json and the zone aliases used by the text
parser (backend/app/ml/text/lexicons/zones.yaml). Zones are places, never people: centroids and polygons only.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "campus"
ZONES_YAML = ROOT / "backend" / "app" / "ml" / "text" / "lexicons" / "zones.yaml"
OVERPASS = "https://overpass-api.de/api/interpreter"
NEIGHBOUR_M = 260  # zones closer than this are one walk apart

# TEMP_DEFAULT: placeholder campus centre until <<CAMPUS_NAME>> is known.
PLACEHOLDER_CENTRE = (17.3850, 78.4867)

KIND_ALIASES = {
    "library": ["library", "lib", "reading room"],
    "canteen": ["canteen", "mess", "cafeteria", "food court", "cafe"],
    "sports": ["sports", "gym", "ground", "playground", "stadium", "court"],
    "hostel": ["hostel", "dorm", "common room"],
    "gate": ["gate", "entrance", "security", "security desk"],
    "admin": ["admin", "administration", "office", "registrar"],
    "academic": ["block", "lecture hall", "classroom", "lab", "department"],
}

# ---- placeholder campus (eight zones, generic names) ------------------------------------

PLACEHOLDER = [
    # id, name, short, kind, (dx, dy) metres from centre
    ("z_library", "Central Library", "Library", "library", (0, 40)),
    ("z_block_a", "Block A Lecture Halls", "Block A", "academic", (-140, 60)),
    ("z_block_b", "Block B Labs", "Block B", "academic", (-90, 190)),
    ("z_gate", "Main Gate and Security Desk", "Main Gate", "gate", (-230, -90)),
    ("z_canteen", "Canteen Court", "Canteen", "canteen", (140, -30)),
    ("z_sports", "Sports Complex", "Sports", "sports", (270, -190)),
    ("z_hostel3", "Hostel 3 Common Room", "Hostel 3", "hostel", (250, 120)),
    ("z_admin", "Admin Block", "Admin", "admin", (-120, -170)),
]
PLACEHOLDER_EDGES = [
    ("z_gate", "z_admin"), ("z_gate", "z_block_a"), ("z_admin", "z_block_a"), ("z_block_a", "z_block_b"),
    ("z_block_a", "z_library"), ("z_library", "z_block_b"), ("z_library", "z_canteen"), ("z_canteen", "z_sports"),
    ("z_canteen", "z_hostel3"), ("z_sports", "z_hostel3"),
]


def offset(lat0: float, lon0: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """(lat, lon) offset by metres east (dx) and north (dy)."""
    return lat0 + dy_m / 111_320.0, lon0 + dx_m / (111_320.0 * math.cos(math.radians(lat0)))


def square(lat: float, lon: float, half_m: float = 55) -> list[list[float]]:
    pts = [(-half_m, -half_m), (half_m, -half_m), (half_m, half_m), (-half_m, half_m), (-half_m, -half_m)]
    return [[round(offset(lat, lon, dx, dy)[1], 6), round(offset(lat, lon, dx, dy)[0], 6)] for dx, dy in pts]


def placeholder(centre: tuple[float, float] = PLACEHOLDER_CENTRE) -> tuple[dict, dict, dict]:
    lat0, lon0 = centre
    feats, aliases = [], {}
    for zid, name, short, kind, (dx, dy) in PLACEHOLDER:
        lat, lon = offset(lat0, lon0, dx, dy)
        feats.append(
            {
                "type": "Feature",
                "properties": {"id": zid, "name": name, "short_name": short, "kind": kind, "centroid": [round(lon, 6), round(lat, 6)]},
                "geometry": {"type": "Polygon", "coordinates": [square(lat, lon)]},
            }
        )
    graph = {"nodes": [z[0] for z in PLACEHOLDER], "edges": [list(e) for e in PLACEHOLDER_EDGES]}
    return {"type": "FeatureCollection", "features": feats, "_note": "TEMP_DEFAULT placeholder campus"}, graph, aliases


# ---- VNR VJIET (real positions) -------------------------------------------------------------
# Positions come from OpenStreetMap (c) contributors, ODbL, except the library, which is not mapped there and is
# approximate. Ids keep the original z_* names where the role is the same, so existing data still lines up.
# id, name, short, kind, lat, lon, aliases
VNRVJIET = [
    ("z_gate", "Main gate and security desk", "Main gate", "gate", 17.5416, 78.38679,
     ["main gate", "gate", "security desk", "security", "security office", "entrance", "atm"]),
    ("z_library", "Central library", "Library", "library", 17.5372, 78.3863,
     ["library", "lib", "central library", "the library", "reading room"]),
    ("z_block_a", "D-Block", "D-Block", "academic", 17.53668, 78.38506,
     ["d block", "d-block", "block d", "lecture hall", "lecture halls", "classroom", "class room"]),
    ("z_block_b", "Workshops", "Workshops", "academic", 17.53728, 78.38526,
     ["workshop", "workshops", "mechanical workshop", "civil workshop", "instrumentation workshop", "lab", "labs"]),
    ("z_canteen", "SAC and food outlets", "SAC", "canteen", 17.53843, 78.38478,
     ["sac", "student activity centre", "student activity center", "canteen", "food court", "food outlets", "cafeteria", "cafe", "coffee day", "amul", "hungry jacks"]),
    ("z_sports", "Sports complex", "Sports", "sports", 17.54066, 78.38545,
     ["sports complex", "sports", "gym", "ground", "playground", "cricket ground", "football ground", "basketball court", "tennis court", "court", "amphitheatre", "amphitheater"]),
    ("z_bus", "Student bus stop", "Bus stop", "transport", 17.53985, 78.38621,
     ["bus stop", "bus", "college bus", "student parking", "parking"]),
    ("z_admin", "Training and placement cell", "Placement cell", "admin", 17.53677, 78.38423,
     ["placement cell", "training and placement", "t&p", "tnp", "office", "admin"]),
]


def vnrvjiet() -> tuple[dict, dict, dict]:
    feats, aliases, pts = [], {}, []
    for zid, name, short, kind, lat, lon, al in VNRVJIET:
        feats.append(
            {
                "type": "Feature",
                "properties": {"id": zid, "name": name, "short_name": short, "kind": kind, "centroid": [lon, lat]},
                "geometry": {"type": "Polygon", "coordinates": [square(lat, lon, 30)]},
            }
        )
        aliases[zid] = al
        pts.append((zid, lat, lon))
    edges = set()
    for zid, la, lo in pts:  # walking links: everything within NEIGHBOUR_M, and never leave a zone stranded
        dists = sorted((haversine_m((la, lo), (lb, ob)), b) for b, lb, ob in pts if b != zid)
        edges.update(tuple(sorted((zid, b))) for d, b in dists if d <= NEIGHBOUR_M)
        if not any(zid in e for e in edges):
            edges.add(tuple(sorted((zid, dists[0][1]))))
    graph = {"nodes": [p[0] for p in pts], "edges": [list(e) for e in sorted(edges)]}
    return {"type": "FeatureCollection", "features": feats, "_note": "VNR VJIET, Bachupally. OpenStreetMap (c) contributors."}, graph, aliases


# ---- OSM path ---------------------------------------------------------------------------


def overpass_query(bbox: str) -> str:
    return f"""[out:json][timeout:60];
(
  way["building"]["name"]({bbox});
  way["amenity"~"library|cafe|restaurant|canteen|food_court"]["name"]({bbox});
  way["leisure"~"sports_centre|pitch|stadium"]({bbox});
  node["barrier"="gate"]({bbox});
  node["entrance"="main"]({bbox});
);
out center tags;"""


def fetch(bbox: str) -> list[dict]:
    data = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode()
    with urllib.request.urlopen(urllib.request.Request(OVERPASS, data=data), timeout=90) as r:
        return json.load(r)["elements"]


def classify(tags: dict) -> str:
    name = (tags.get("name") or "").lower()
    if tags.get("amenity") == "library" or "library" in name:
        return "library"
    if tags.get("amenity") in ("cafe", "restaurant", "canteen", "food_court") or re.search(r"canteen|mess|cafeteria|food", name):
        return "canteen"
    if tags.get("leisure") or re.search(r"sport|gym|stadium|ground", name):
        return "sports"
    if tags.get("building") == "dormitory" or re.search(r"hostel|dorm|residence", name):
        return "hostel"
    if tags.get("barrier") == "gate" or tags.get("entrance") or re.search(r"gate|security", name):
        return "gate"
    if re.search(r"admin|registrar|office", name):
        return "admin"
    return "academic"


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    h = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(h))


def build_from_elements(elements: list[dict]) -> tuple[dict, dict, dict]:
    """Group named places into zones, merge academic buildings into a few blocks, link near zones."""
    places: list[dict] = []
    for el in elements:
        tags = el.get("tags", {})
        c = el.get("center") or ({"lat": el["lat"], "lon": el["lon"]} if "lat" in el else None)
        if not c:
            continue
        places.append({"name": tags.get("name") or tags.get("ref") or classify(tags).title(), "kind": classify(tags), "lat": c["lat"], "lon": c["lon"]})
    if not places:
        raise SystemExit("No named places found in that area. Try a larger bbox, or use --placeholder.")

    academic = [p for p in places if p["kind"] == "academic"]
    others = [p for p in places if p["kind"] != "academic"]
    if len(academic) > 4:  # cluster the many small academic buildings into at most four blocks
        from sklearn.cluster import KMeans

        xy = [[p["lat"], p["lon"]] for p in academic]
        km = KMeans(n_clusters=4, n_init=5, random_state=0).fit(xy)
        merged = []
        for i in range(4):
            members = [p for p, lab in zip(academic, km.labels_) if lab == i]
            merged.append({"name": f"Academic Block {chr(65 + i)}", "kind": "academic", "lat": float(km.cluster_centers_[i][0]), "lon": float(km.cluster_centers_[i][1]), "members": members})
        academic = merged

    zones = []
    for i, p in enumerate(academic + others):
        slug = re.sub(r"[^a-z0-9]+", "_", p["name"].lower()).strip("_")[:24]
        zones.append({"id": f"z_{slug}", "name": p["name"], "short_name": p["name"].split(" and ")[0][:24], "kind": p["kind"], "lat": p["lat"], "lon": p["lon"]})
    seen: set[str] = set()
    for z in zones:  # make ids unique
        base, n = z["id"], 2
        while z["id"] in seen:
            z["id"], n = f"{base}_{n}", n + 1
        seen.add(z["id"])

    feats, aliases = [], {}
    for z in zones:
        feats.append(
            {
                "type": "Feature",
                "properties": {"id": z["id"], "name": z["name"], "short_name": z["short_name"], "kind": z["kind"], "centroid": [round(z["lon"], 6), round(z["lat"], 6)]},
                "geometry": {"type": "Polygon", "coordinates": [square(z["lat"], z["lon"], 45)]},
            }
        )
        aliases[z["id"]] = sorted({z["name"].lower(), z["short_name"].lower(), *KIND_ALIASES.get(z["kind"], [])})

    edges = set()
    for i, a in enumerate(zones):
        dists = sorted(((haversine_m((a["lat"], a["lon"]), (b["lat"], b["lon"])), b["id"]) for b in zones if b is not a))
        for d, bid in dists:
            if d <= NEIGHBOUR_M:
                edges.add(tuple(sorted((a["id"], bid))))
        if dists and not any(a["id"] in e for e in edges):  # never leave a zone unreachable
            edges.add(tuple(sorted((a["id"], dists[0][1]))))
    graph = {"nodes": [z["id"] for z in zones], "edges": [list(e) for e in sorted(edges)]}
    return {"type": "FeatureCollection", "features": feats}, graph, aliases


def write(geo: dict, graph: dict, aliases: dict | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "zones.geojson").write_text(json.dumps(geo, indent=2))
    (OUT / "zone_graph.json").write_text(json.dumps(graph, indent=2))
    if aliases:
        ZONES_YAML.write_text("# Generated by scripts/build_campus_zones.py\n" + yaml.safe_dump({"zones": aliases}, sort_keys=True))
    print(f"wrote {len(geo['features'])} zones and {len(graph['edges'])} walking links to {OUT}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--vnrvjiet", action="store_true", help="write the VNR VJIET zones (real positions from OpenStreetMap)")
    src.add_argument("--placeholder", action="store_true", help="write the eight generic zones (TEMP_DEFAULT centre)")
    src.add_argument("--bbox", help="south,west,north,east")
    src.add_argument("--elements", help="path to a saved Overpass JSON response (offline)")
    ap.add_argument("--centre", help="lat,lon for --placeholder")
    args = ap.parse_args()

    if args.vnrvjiet:
        geo, graph, aliases = vnrvjiet()
        write(geo, graph, aliases)
        return 0
    if args.placeholder:
        centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else PLACEHOLDER_CENTRE
        geo, graph, _ = placeholder(centre)  # type: ignore[arg-type]
        write(geo, graph, None)  # the checked-in zones.yaml already has the placeholder aliases
        return 0
    elements = json.loads(Path(args.elements).read_text())["elements"] if args.elements else fetch(args.bbox)
    geo, graph, aliases = build_from_elements(elements)
    write(geo, graph, aliases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
