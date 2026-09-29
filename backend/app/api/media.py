from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..errors import ApiError
from ..models import STAFF_ROLES, ItemImage, User
from ..services.media import media_root

router = APIRouter(tags=["media"])


def _image(db: Session, image_id: str) -> ItemImage:
    try:
        row = db.get(ItemImage, uuid.UUID(image_id))
    except ValueError:
        row = None
    if row is None:
        raise ApiError(404, "not_found", "That photo isn't here.")
    return row


@router.get("/media/public/{image_id}.jpg")
def public_photo(image_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """The blurred copy (or a solid plate for a redacted ID card). Public by design, so <img> tags work."""
    row = _image(db, image_id)
    if not row.public_path or not (media_root() / row.public_path).exists():
        raise ApiError(404, "not_found", "That photo isn't ready yet.")
    return FileResponse(media_root() / row.public_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/media/original/{image_id}")
def original_photo(image_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> FileResponse:
    row = _image(db, image_id)
    if row.item.owner_id != user.id and user.role not in STAFF_ROLES:
        raise ApiError(404, "not_found", "That photo isn't here.")
    path = media_root() / row.path
    if not path.exists():
        raise ApiError(404, "not_found", "That photo isn't ready yet.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})
