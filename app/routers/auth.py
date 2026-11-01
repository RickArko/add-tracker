import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import now_utc
from app.mailer import send_quietly
from app.models import AuthToken, User
from app.schemas import (
    AccountDelete,
    AuthStatus,
    Credentials,
    EmailAdd,
    EmailRequest,
    LoginBody,
    PasswordChange,
    PasswordConfirm,
    RecoverBody,
    TokenBody,
    TokenReset,
    UserOut,
    WithRecoveryCode,
)
from app.security import (
    current_user,
    email_hash,
    end_all_sessions,
    end_other_sessions,
    end_session,
    get_db,
    hash_password,
    hash_token,
    new_recovery_code,
    normalize_recovery_code,
    optional_user,
    start_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        username=user.username,
        has_recovery_code=user.recovery_code_hash is not None,
        has_email=user.email_hash is not None,
    )


def _with_code(user: User, code: str) -> WithRecoveryCode:
    return WithRecoveryCode(**_user_out(user).model_dump(), recovery_code=code)


def _set_passphrase(db: Session, user: User, password: str, *, keep_email: bool = False) -> str:
    """Sets a passphrase and cancels every recovery route from before it, returning a new code.

    Someone who once knew the old passphrase may have added their own code or email, so none
    of those can survive. Returns the replacement recovery code.
    """
    user.password_hash = hash_password(password)
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    if not keep_email:
        user.email_hash = None
    code = new_recovery_code()
    user.recovery_code_hash = hash_password(code)
    return code


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
        user=_user_out(user) if user else None,
        signup_open=_signup_open(request, db),
        first_run=db.scalar(select(func.count()).select_from(User)) == 0,
        email_enabled=request.app.state.mailer is not None,
    )


@router.post("/register", status_code=201)
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> WithRecoveryCode:
    if not _signup_open(request, db):
        raise HTTPException(status_code=403, detail="This server isn't accepting new accounts.")
    password_hash = hash_password(body.password)
    code = new_recovery_code()
    code_hash = hash_password(code)
    # Held across the check and the insert, so parallel requests can't all pass as "first".
    with request.app.state.signup_lock:
        db.rollback()
        if not _signup_open(request, db):
            raise HTTPException(status_code=403, detail="This server isn't accepting new accounts.")
        user = User(
            username=body.username,
            password_hash=password_hash,
            recovery_code_hash=code_hash,
            created_at=now_utc(),
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="That username is taken.") from exc
        start_session(db, user, request, response)
        db.commit()
    return _with_code(user, code)


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
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    end_session(db, request, response)
    db.commit()


@router.post("/password")
def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WithRecoveryCode:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=403, detail="Current passphrase is incorrect.")
    code = _set_passphrase(db, user, body.new_password)
    end_other_sessions(db, user, request)
    db.commit()
    return _with_code(user, code)


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


# --- Recovery code ---


@router.post("/recovery-code")
def create_recovery_code(
    body: PasswordConfirm,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WithRecoveryCode:
    """Replaces any earlier code, so a lost or exposed one stops working."""
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=403, detail="Passphrase is incorrect.")
    code = new_recovery_code()
    user.recovery_code_hash = hash_password(code)
    db.commit()
    return _with_code(user, code)


@router.post("/recover")
def recover_with_code(
    body: RecoverBody, request: Request, response: Response, db: Session = Depends(get_db)
) -> WithRecoveryCode:
    # No per-username limit: a code can't be guessed at 100 bits, and a limit here would let
    # anyone lock the real owner out of their own recovery by failing on purpose.
    username = body.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    used_hash = user.recovery_code_hash if user else None
    if not verify_password(used_hash, normalize_recovery_code(body.recovery_code)):
        raise HTTPException(status_code=401, detail="Username or recovery code is incorrect.")
    # Spends the code atomically, so two requests can't both win and leave a dead replacement.
    spent = db.execute(
        update(User)
        .where(User.id == user.id, User.recovery_code_hash == used_hash)
        .values(recovery_code_hash=None)
    )
    if spent.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=401, detail="Username or recovery code is incorrect.")
    db.refresh(user)
    fresh = _set_passphrase(db, user, body.new_password)
    end_all_sessions(db, user)
    start_session(db, user, request, response)
    db.commit()
    return _with_code(user, fresh)


# --- Optional email ---

RESET_LIFETIME = timedelta(minutes=30)
CONFIRM_LIFETIME = timedelta(hours=24)


def _mailer(request: Request):
    mailer = request.app.state.mailer
    if mailer is None:
        raise HTTPException(status_code=404, detail="Email recovery isn't turned on.")
    return mailer


def _issue_token(
    db: Session, user: User, purpose: str, lifetime: timedelta, hashed_email: str | None = None
) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthToken).where(AuthToken.expires_at < now_utc()))
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == purpose))
    db.add(
        AuthToken(
            token_hash=hash_token(token),
            user_id=user.id,
            purpose=purpose,
            email_hash=hashed_email,
            expires_at=now_utc() + lifetime,
        )
    )
    return token


def _use_token(db: Session, token: str, purpose: str) -> tuple[int, str | None]:
    """Spends a token atomically, so parallel requests can't all succeed with one link."""
    row = db.execute(
        delete(AuthToken)
        .where(
            AuthToken.token_hash == hash_token(token),
            AuthToken.purpose == purpose,
            AuthToken.expires_at >= now_utc(),
        )
        .returning(AuthToken.user_id, AuthToken.email_hash)
    ).first()
    if row is None:
        raise HTTPException(
            status_code=400, detail="This link has expired or was already used. Request a new one."
        )
    return row.user_id, row.email_hash


def _within_email_limits(request: Request, flow: str, hashed_email: str) -> bool:
    """Caps mail per address and per flow overall, so this can't be used to pester anyone.

    Flows have separate budgets, so anonymous reset requests can't use up what signed-in
    people need, and one flow's limit can't be used to learn whether an address is registered.
    """
    state = request.app.state
    return state.email_address_throttle.reserve(
        f"{flow}:{hashed_email}"
    ) and state.email_flow_throttle.reserve(flow)


@router.post("/email", status_code=202)
def add_email(
    body: EmailAdd,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    mailer = _mailer(request)
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=403, detail="Passphrase is incorrect.")
    settings = request.app.state.settings
    hashed = email_hash(body.email, settings.email_pepper)
    if not _within_email_limits(request, "add", hashed):
        raise HTTPException(status_code=429, detail="Too many emails. Try again later.")
    token = _issue_token(db, user, "confirm", CONFIRM_LIFETIME, hashed)
    db.commit()
    link = f"{settings.public_url}/confirm-email?token={token}"
    background.add_task(
        send_quietly,
        mailer,
        body.email,
        "Confirm your recovery email",
        f"Open this link within 24 hours to use this address for account recovery:\n\n{link}\n\n"
        "If you didn't ask for this, ignore this email and nothing will change.\n",
    )
    return {"status": "sent"}


@router.post("/email/confirm")
def confirm_email(
    body: TokenBody, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict[str, str]:
    """Needs the owner's session, so a mail scanner or stranger can't attach an address."""
    owner_id, hashed = _use_token(db, body.token, "confirm")
    if owner_id != user.id:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Log in to the account that asked for this link, then try again.",
        )
    user.email_hash = hashed
    # Links sent to any earlier address stop working.
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    db.commit()
    return {"status": "confirmed"}


@router.delete("/email", status_code=204)
def remove_email(
    body: PasswordConfirm,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=403, detail="Passphrase is incorrect.")
    user.email_hash = None
    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    db.commit()


@router.post("/email/reset-request", status_code=202)
def request_email_reset(
    body: EmailRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """The reply is the same whether or not the address is on an account."""
    mailer = _mailer(request)
    settings = request.app.state.settings
    hashed = email_hash(body.email, settings.email_pepper)
    users = db.scalars(select(User).where(User.email_hash == hashed)).all()
    if users and _within_email_limits(request, "reset", hashed):
        lines = []
        for user in users:
            token = _issue_token(db, user, "reset", RESET_LIFETIME)
            lines.append(f"{user.username}: {settings.public_url}/reset?token={token}")
        db.commit()
        listing = "\n".join(lines)
        background.add_task(
            send_quietly,
            mailer,
            body.email,
            "Reset your passphrase",
            f"Open the link for your username within 30 minutes to set a new passphrase:\n\n"
            f"{listing}\n\nIf you didn't ask for this, ignore this email. "
            "Your passphrase hasn't changed.\n",
        )
    return {"status": "sent"}


@router.post("/email/reset")
def reset_with_email(
    body: TokenReset, request: Request, response: Response, db: Session = Depends(get_db)
) -> WithRecoveryCode:
    owner_id, _ = _use_token(db, body.token, "reset")
    user = db.get(User, owner_id)
    # This address just proved itself, so it stays; every other route is cancelled.
    code = _set_passphrase(db, user, body.new_password, keep_email=True)
    end_all_sessions(db, user)
    start_session(db, user, request, response)
    db.commit()
    return _with_code(user, code)
