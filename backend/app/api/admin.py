from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ROOT, get_settings
from ..db import get_db
from ..deps import AdminOnly, DeskOrAdmin
from ..errors import ApiError
from ..ml import registry
from ..models import Claim, User
from ..services import insights, routing
from ..services.serializers import claim_out

router = APIRouter(prefix="/admin", tags=["admin"])
REPORTS = ROOT / "eval" / "reports"


def _range(r: str) -> str:
    if r not in insights.RANGES:
        raise ApiError(422, "invalid_request", "Range must be 7d, 30d or term.", {"range": "7d, 30d or term"})
    return r


@router.get("/claims")
def claims(status: str | None = None, _: User = Depends(DeskOrAdmin), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Claim).order_by(Claim.created_at.desc()).limit(300)
    if status:
        stmt = stmt.where(Claim.status == status)
    return [claim_out(c, staff=True) for c in db.scalars(stmt)]


@router.get("/insights/summary")
def summary(range: str = "7d", _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> dict:
    return insights.summary(db, _range(range))


@router.get("/insights/hotspots")
def hotspots(range: str = "7d", _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> list[dict]:
    return insights.hotspots(db, _range(range))


@router.get("/insights/heatmap")
def heatmap(range: str = "7d", _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> list[list[int]]:
    return insights.heatmap(db, _range(range))


@router.get("/insights/categories")
def categories(range: str = "7d", _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> list[dict]:
    return insights.categories(db, _range(range))


@router.get("/insights/finders")
def finders(range: str = "7d", _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> list[dict]:
    return insights.finders(db, _range(range))


@router.get("/ops/scene")
def scene(from_: datetime | None = None, to: datetime | None = None, _: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> dict:
    return insights.ops_scene(db, from_, to)


@router.get("/eval/reports")
def eval_reports(_: User = Depends(AdminOnly)) -> list[dict]:
    out = []
    for p in sorted(REPORTS.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        out.append({"run_id": data.get("run_id", p.stem), "pairs": data.get("pairs"), "created_at": data.get("created_at")})
    return out


@router.get("/eval/reports/{run_id}")
def eval_report(run_id: str, _: User = Depends(AdminOnly)) -> dict:
    p = REPORTS / f"{run_id}.json"
    if "/" in run_id or ".." in run_id or not p.exists():
        raise ApiError(404, "not_found", "That report isn't here.")
    data = json.loads(p.read_text())
    card = get_settings().weights_path / "model_card.json"
    data["model_card"] = json.loads(card.read_text()) if card.exists() else None
    data["stages"] = registry.status()
    return data


@router.post("/maintenance/route-unclaimed")
def route_unclaimed(_: User = Depends(AdminOnly), db: Session = Depends(get_db)) -> dict:
    return {"routed": routing.route_unclaimed(db)}
