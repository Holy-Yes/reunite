#!/usr/bin/env python
"""Bring the zones table in line with config/campus/zones.geojson (the API only loads it into an empty table).

    backend/../.venv/bin/python scripts/sync_zones.py [--rename OLD=NEW ...]

Adds new zones, updates existing ones, and moves items from a renamed zone id to its new id. Zones that are no
longer in the file but still have items are kept and reported, so nothing is orphaned.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select, update  # noqa: E402

from app.db import configure, session_scope  # noqa: E402
from app.models import Item, Zone  # noqa: E402
from app.taxonomy import zone_aliases  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rename", action="append", default=[], metavar="OLD=NEW", help="move items from zone OLD to NEW")
    args = ap.parse_args()
    aliases = zone_aliases()
    feats = json.loads((ROOT / "config/campus/zones.geojson").read_text())["features"]
    configure()
    with session_scope() as db:
        have = {z.id: z for z in db.scalars(select(Zone))}
        for f in feats:
            p = f["properties"]
            lon, lat = p["centroid"]
            row = have.get(p["id"]) or Zone(id=p["id"])
            row.name, row.short_name, row.kind = p["name"], p["short_name"], p["kind"]
            row.centroid_lon, row.centroid_lat, row.polygon, row.aliases = lon, lat, f["geometry"], aliases.get(p["id"], [])
            db.add(row)
        db.flush()
        for pair in args.rename:
            old, new = pair.split("=")
            db.execute(update(Item).where(Item.zone_id == old).values(zone_id=new))
            db.execute(update(Item).where(Item.custody_zone_id == old).values(custody_zone_id=new))
        keep = {f["properties"]["id"] for f in feats}
        for zid, z in have.items():
            if zid in keep:
                continue
            used = db.scalar(select(Item.id).where((Item.zone_id == zid) | (Item.custody_zone_id == zid)).limit(1))
            if used:
                print(f"kept {zid}: items still use it")
            else:
                db.delete(z)
                print(f"removed {zid}")
    print(f"synced {len(feats)} zones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
