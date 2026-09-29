from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_user
from ..errors import ApiError
from ..models import STAFF_ROLES, OtpCode, PushSubscription, User
from ..security import create_access_token, new_code, otp_hash
from ..services.notify import send_email
from ..services.serializers import user_out

router = APIRouter(tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_REQUESTS_PER_HOUR = 5


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class OtpRequest(BaseModel):
    email: str


class OtpVerify(BaseModel):
    email: str
    code: str


class MeUpdate(BaseModel):
    notify_push: bool | None = None
    notify_email: bool | None = None
    roll_no: str | None = None
    venue: str | None = None


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSub(BaseModel):
    endpoint: str
    keys: PushKeys


def _email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(422, "invalid_email", "Enter a valid email address.", {"email": "invalid"})
    domains = get_settings().domains
    if domains and email.split("@")[-1] not in domains:
        raise ApiError(422, "email_domain", f"Use your college email ({', '.join('@' + d for d in domains)}).", {"email": "domain not allowed"})
    return email


@router.get("/auth/config")
def auth_config() -> dict:
    """Lets the sign-in page show the code in demo mode. `demo_otp` is null unless DEMO_OTP is set."""
    return {"demo_otp": get_settings().demo_otp or None}


@router.post("/auth/otp/request", status_code=204)
def request_code(body: OtpRequest, db: Session = Depends(get_db)) -> Response:
    s = get_settings()
    email = _email(body.email)
    now = datetime.now(timezone.utc)
    recent = db.scalar(select(func.count(OtpCode.id)).where(OtpCode.email == email, OtpCode.created_at >= now - timedelta(hours=1))) or 0
    if recent >= MAX_REQUESTS_PER_HOUR:
        raise ApiError(429, "otp_rate_limited", "Too many codes requested. Try again in a while.", retry_after=3600)
    code = s.demo_otp if s.demo_otp else new_code()
    db.add(OtpCode(email=email, code_hash=otp_hash(email, code), expires_at=now + timedelta(minutes=s.otp_ttl_minutes)))
    db.commit()
    send_email(email, "Your Reunite sign-in code", f"Your code is {code}. It works for {s.otp_ttl_minutes} minutes.")
    return Response(status_code=204)


@router.post("/auth/otp/verify")
def verify_code(body: OtpVerify, db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    email = _email(body.email)
    now = datetime.now(timezone.utc)
    otp = db.scalar(select(OtpCode).where(OtpCode.email == email, OtpCode.consumed_at.is_(None)).order_by(OtpCode.created_at.desc()).limit(1))
    if otp is None or aware(otp.expires_at) < now:
        raise ApiError(400, "invalid_code", "That code doesn't match. Check the latest email.")
    if otp.attempts >= s.otp_max_attempts:
        raise ApiError(429, "otp_locked", "Too many tries. Request a new code.", retry_after=600)
    if otp_hash(email, body.code.strip()) != otp.code_hash:
        otp.attempts += 1
        db.commit()
        raise ApiError(400, "invalid_code", "That code doesn't match. Check the latest email.", {"attempts_left": str(max(s.otp_max_attempts - otp.attempts, 0))})
    otp.consumed_at = now
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        role = "admin" if email in s.admins else "desk" if email in s.desks else "security_guard" if email in s.guards else "student"
        user = User(email=email, role=role)
        db.add(user)
    db.commit()
    return {"token": create_access_token(user.id, user.role), "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


@router.patch("/me")
def update_me(body: MeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.notify_push is not None:
        user.notify_push = body.notify_push
    if body.notify_email is not None:
        user.notify_email = body.notify_email
    if body.venue is not None:
        if user.role not in STAFF_ROLES:
            raise ApiError(403, "forbidden", "Only desk staff have a venue.")
        user.venue = body.venue.strip()[:80] or None
    if body.roll_no is not None:
        roll = body.roll_no.strip().upper()
        if roll and not re.fullmatch(get_settings().roll_no_regex, roll):
            raise ApiError(422, "invalid_roll_no", "That doesn't look like a roll number here. It should look like 21071A0542.", {"roll_no": "invalid"})
        if roll and db.scalar(select(User.id).where(User.roll_no == roll, User.id != user.id)):
            raise ApiError(409, "roll_no_taken", "That roll number is already on another account.")
        user.roll_no = roll or None
    db.commit()
    return user_out(user)


@router.get("/users/me/trust")
def my_trust(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..services.trust import trust_for

    return trust_for(db, user)


@router.post("/me/push-subscription", status_code=204)
def push_subscription(body: PushSub, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth))
    else:
        sub.user_id, sub.p256dh, sub.auth = user.id, body.keys.p256dh, body.keys.auth
    db.commit()
    return Response(status_code=204)
