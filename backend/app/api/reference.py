from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import User
from ..services.zones import zones_payload
from ..taxonomy import taxonomy_payload

router = APIRouter(tags=["reference"])


@router.get("/taxonomy")
def taxonomy(_: User = Depends(current_user)) -> dict:
    return taxonomy_payload()


@router.get("/zones")
def zones(_: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return zones_payload(db)
