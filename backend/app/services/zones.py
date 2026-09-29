from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ROOT
from ..models import Zone

CONFIG = ROOT / "config" / "campus"


def load_zones(db: Session) -> int:
    """Insert zones from config/campus/zones.geojson when the table is empty. Returns how many were added."""
    if db.scalar(select(Zone.id).limit(1)):
        return 0
    path = CONFIG / "zones.geojson"
    if not path.exists():
        return 0
    from ..taxonomy import zone_aliases

    aliases = zone_aliases()
    n = 0
    for f in json.loads(path.read_text())["features"]:
        p = f["properties"]
        lon, lat = p["centroid"]
        db.add(
            Zone(
                id=p["id"], name=p["name"], short_name=p["short_name"], kind=p["kind"],
                centroid_lon=lon, centroid_lat=lat, polygon=f["geometry"], aliases=aliases.get(p["id"], []),
            )
        )
        n += 1
    db.commit()
    return n


def zone_names(db: Session) -> dict[str, str]:
    return {z.id: z.name for z in db.scalars(select(Zone))}


def zones_payload(db: Session) -> dict:
    graph = {}
    p = CONFIG / "zone_graph.json"
    if p.exists():
        graph = json.loads(p.read_text())
    feats = [
        {
            "type": "Feature",
            "properties": {"id": z.id, "name": z.name, "short_name": z.short_name, "kind": z.kind, "centroid": [z.centroid_lon, z.centroid_lat]},
            "geometry": z.polygon,
        }
        for z in db.scalars(select(Zone).order_by(Zone.name))
    ]
    return {"type": "FeatureCollection", "features": feats, "graph": graph}


def nearest_zone(db: Session, lat: float, lon: float) -> str | None:
    """The zone whose centre is closest to a point, so a map pin can stand in for picking a place from the list."""
    import math

    best, best_d = None, math.inf
    for z in db.scalars(select(Zone)):
        dy = (z.centroid_lat - lat) * 110_540
        dx = (z.centroid_lon - lon) * 111_320 * math.cos(math.radians(lat))
        d = dx * dx + dy * dy
        if d < best_d:
            best, best_d = z.id, d
    return best
