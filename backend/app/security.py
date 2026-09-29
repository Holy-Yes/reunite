from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from .config import get_settings

ALGO = "HS256"
TOKEN_TTL = timedelta(days=7)


class TokenError(Exception):
    pass


def _secret() -> str:
    return get_settings().jwt_secret


# ---- access tokens ----------------------------------------------------------


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "typ": "access", "iat": now, "exp": now + TOKEN_TTL},
        _secret(),
        algorithm=ALGO,
    )


def decode_access_token(token: str) -> dict:
    try:
        data = jwt.decode(token, _secret(), algorithms=[ALGO])
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
    if data.get("typ") != "access":
        raise TokenError("wrong token type")
    return data


# ---- one-time codes ---------------------------------------------------------


def new_code() -> str:
    """Six random digits."""
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_hash(email: str, code: str) -> str:
    return hmac.new(_secret().encode(), f"otp|{email.lower()}|{code}".encode(), hashlib.sha256).hexdigest()


def salted_hash(code: str, salt: str | None = None) -> str:
    """`salt$hash` for handover codes. The code space is small, so attempts are limited elsewhere."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt.encode(), 60_000).hex()
    return f"{salt}${digest}"


def verify_salted(code: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(salted_hash(code, salt), stored)


# ---- handover tokens (the QR payload) -----------------------------------------


def make_handover_token(claim_id: uuid.UUID, jti: str, expires_at: datetime) -> str:
    return jwt.encode(
        {"typ": "handover", "claim": str(claim_id), "jti": jti, "exp": expires_at},
        _secret(),
        algorithm=ALGO,
    )


def read_handover_token(token: str) -> dict:
    try:
        data = jwt.decode(token, _secret(), algorithms=[ALGO])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("expired") from e
    except jwt.PyJWTError as e:
        raise TokenError("invalid") from e
    if data.get("typ") != "handover":
        raise TokenError("invalid")
    return data
