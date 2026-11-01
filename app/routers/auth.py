from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import now_utc
from app.models import User
from app.schemas import AccountDelete, AuthStatus, Credentials, LoginBody, PasswordChange, UserOut
from app.security import (
    current_user,
    end_other_sessions,
    end_session,
    get_db,
    hash_password,
    optional_user,
    start_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _signup_open(request: Request, db: Session) -> bool:
    mode = request.app.state.settings.signup
    if mode == "open":
        return True
    if mode == "closed":
        return False
    return db.scalar(select(func.count()).select_from(User)) == 0


@router.get("/status")
def status(
    request: Request,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> AuthStatus:
    return AuthStatus(
        user=UserOut(username=user.username) if user else None,
        signup_open=_signup_open(request, db),
        first_run=db.scalar(select(func.count()).select_from(User)) == 0,
    )


@router.post("/register", status_code=201)
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    if not _signup_open(request, db):
        raise HTTPException(status_code=403, detail="This server isn't accepting new accounts.")
    password_hash = hash_password(body.password)
    # Held across the check and the insert, so parallel requests can't all pass as "first".
    with request.app.state.signup_lock:
        db.rollback()
        if not _signup_open(request, db):
            raise HTTPException(status_code=403, detail="This server isn't accepting new accounts.")
        user = User(username=body.username, password_hash=password_hash, created_at=now_utc())
        db.add(user)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="That username is taken.") from exc
        start_session(db, user, request, response)
        db.commit()
    return UserOut(username=user.username)


@router.post("/login")
def login(
    body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    username = body.username.strip().lower()
    throttle = request.app.state.login_throttle
    if not throttle.reserve(username):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.username == username))
    if not verify_password(user.password_hash if user else None, body.password):
        raise HTTPException(status_code=401, detail="Username or passphrase is incorrect.")
    throttle.reset(username)
    start_session(db, user, request, response)
    db.commit()
    return UserOut(username=user.username)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    end_session(db, request, response)
    db.commit()


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=403, detail="Current passphrase is incorrect.")
    user.password_hash = hash_password(body.new_password)
    end_other_sessions(db, user, request)
    db.commit()


@router.delete("/account", status_code=204)
def delete_account(
    body: AccountDelete,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=403, detail="Passphrase is incorrect.")
    db.delete(user)
    db.commit()
    response.delete_cookie("tally_session", path="/")
