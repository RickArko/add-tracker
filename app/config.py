"""Runtime configuration, read from TALLY_* environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SignupMode = Literal["first", "open", "closed"]


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/tally.db")
    # "first": only the first account may register (the safe default for a personal install).
    signup: SignupMode = "first"
    secure_cookies: bool = False
    session_days: int = 30
    frontend_dist: Path = Path("frontend/dist")
    # Optional email recovery. It stays off and hidden until these are all set.
    public_url: str = ""
    email_pepper: str = ""
    email_from: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_outbox: Path | None = None

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


def load_settings() -> Settings:
    signup = os.environ.get("TALLY_SIGNUP", "first")
    if signup not in ("first", "open", "closed"):
        raise ValueError("TALLY_SIGNUP must be one of: first, open, closed")
    return Settings(
        db_path=Path(os.environ.get("TALLY_DB_PATH", "data/tally.db")),
        signup=signup,
        secure_cookies=os.environ.get("TALLY_SECURE_COOKIES", "0") == "1",
        session_days=int(os.environ.get("TALLY_SESSION_DAYS", "30")),
        frontend_dist=Path(os.environ.get("TALLY_FRONTEND_DIST", "frontend/dist")),
        public_url=os.environ.get("TALLY_PUBLIC_URL", "").rstrip("/"),
        email_pepper=os.environ.get("TALLY_EMAIL_PEPPER", ""),
        email_from=os.environ.get("TALLY_EMAIL_FROM", ""),
        smtp_host=os.environ.get("TALLY_SMTP_HOST", ""),
        smtp_port=int(os.environ.get("TALLY_SMTP_PORT", "587")),
        smtp_user=os.environ.get("TALLY_SMTP_USER", ""),
        smtp_password=os.environ.get("TALLY_SMTP_PASSWORD", ""),
        email_outbox=Path(p) if (p := os.environ.get("TALLY_EMAIL_OUTBOX")) else None,
    )
