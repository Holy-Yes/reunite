from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .db import get_db
from .errors import ApiError
from .models import User
from .security import TokenError, decode_access_token


def current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Sign in to continue.")
    try:
        data = decode_access_token(authorization.split(" ", 1)[1].strip())
    except TokenError:
        raise ApiError(401, "unauthorized", "Your session has expired. Sign in again.")
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None:
        raise ApiError(401, "unauthorized", "Sign in to continue.")
    return user


def require_role(*roles: str) -> Callable[[User], User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise ApiError(403, "forbidden", "You don't have access to this.")
        return user

    return dep


DeskOrAdmin = require_role("desk", "admin")
AdminOnly = require_role("admin")
