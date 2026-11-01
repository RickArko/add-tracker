"""Password hashing, session tokens, login throttling, and the current-user dependency."""

import hashlib
import secrets
import threading
import time
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import now_utc
from app.models import AuthSession, User

COOKIE_NAME = "tally_session"
_hasher = PasswordHasher()
# Verified against when a username does not exist, so response time doesn't reveal which do.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        ok = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and password_hash is not None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, request: Request, response: Response) -> None:
    settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now_utc()))
    db.add(
        AuthSession(
            token_hash=_hash_token(token),
            user_id=user.id,
            expires_at=now_utc() + timedelta(days=settings.session_days),
        )
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="strict",
        secure=settings.secure_cookies,
        path="/",
    )


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
    response.delete_cookie(COOKIE_NAME, path="/")


def end_other_sessions(db: Session, user: User, request: Request) -> None:
    current = _hash_token(request.cookies.get(COOKIE_NAME, ""))
    db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.token_hash != current)
    )


def get_db(request: Request):
    with request.app.state.sessionmaker() as db:
        yield db


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = db.get(AuthSession, _hash_token(token))
    if session is None or session.expires_at < now_utc():
        return None
    return db.get(User, session.user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to continue.")
    return user


class LoginThrottle:
    """Allows `limit` failed logins per username per `window` seconds.

    In-memory, which fits the single-instance SQLite deployment. Keyed on username rather
    than IP so distributed guessing against one account is still stopped.
    """

    def __init__(self, limit: int = 5, window: float = 900, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        cutoff = self.clock() - self.window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def record_failure(self, key: str) -> None:
        with self._lock:
            if len(self._failures) > 10_000:
                for existing in list(self._failures):
                    self._recent(existing)
            self._failures.setdefault(key, []).append(self.clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
