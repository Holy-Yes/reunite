from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    """All configuration, from environment or `.env` (see .env.example and IMPLEMENTATION_PLAN section 16)."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localhost/reunite"
    jwt_secret: str  # required
    allowed_email_domains: str = ""
    cors_origins: str = "http://localhost:5190,http://127.0.0.1:5190"
    media_dir: str = "data/media"
    device: str = "auto"
    ml_mode: str = "full"

    notify_threshold: float = 0.60
    band_strong: float = 0.75
    band_possible: float = 0.40
    min_show: float = 0.20
    always_review: str = "laptop,phone,id_card"
    roll_no_regex: str = r"\d{2}07[15]A[0-9A-Z]{4}"  # VNR VJIET: 21071A0542 = year, college 07, regular (1) or lateral (5), A, branch and serial
    retention_days: int = 90
    unclaimed_route_days: int = 30   # found items nobody claimed go to the desk below after this many days (0 = off)
    unclaimed_route_zone: str = "z_gate"
    unclaimed_route_label: str = "the campus security desk"

    # Demo only: when set, every sign-in code is this value and the sign-in page shows it. Leave empty in production.
    demo_otp: str = ""
    email_backend: str = "console"
    smtp_host: str = ""
    smtp_user: str = ""
    smtp_password: str = ""
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@example.com"
    campus_name: str = "<<CAMPUS_NAME>>"
    admin_emails: str = ""  # bootstrap: these addresses get role admin on first sign-in
    desk_emails: str = ""
    security_guard_emails: str = ""

    # Fixed by the plan, exposed for tests.
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    handover_ttl_minutes: int = 15
    handover_max_attempts: int = 5
    candidate_pool: int = 50
    finder_points: int = 10

    @property
    def domains(self) -> list[str]:
        return [d.lower().lstrip("@") for d in _csv(self.allowed_email_domains)]

    @property
    def admins(self) -> set[str]:
        return {e.lower() for e in _csv(self.admin_emails)}

    @property
    def desks(self) -> set[str]:
        return {e.lower() for e in _csv(self.desk_emails)}

    @property
    def guards(self) -> set[str]:
        return {e.lower() for e in _csv(self.security_guard_emails)}

    @property
    def origins(self) -> list[str]:
        return _csv(self.cors_origins)

    @property
    def review_categories(self) -> set[str]:
        return set(_csv(self.always_review))

    @property
    def media_path(self) -> Path:
        p = Path(self.media_dir)
        return p if p.is_absolute() else ROOT / p

    @property
    def weights_path(self) -> Path:
        return BACKEND / "weights"

    @property
    def light_ml(self) -> bool:
        return self.ml_mode.lower() == "light"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings() -> None:
    get_settings.cache_clear()
