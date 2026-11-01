"""Operator commands: reset a passphrase, or fill a throwaway database with sample data.

Usage:
    uv run python -m app.cli reset-password <username>
    uv run python -m app.cli backup <file>      # a consistent copy, safe while the app runs
    uv run python -m app.cli seed-demo          # requires TALLY_DB_PATH to be set
"""

import getpass
import os
import random
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.db import make_engine, now_utc, run_migrations
from app.models import AuthSession, AuthToken, Entry, LimitPeriod, Tracker, User
from app.security import hash_password

DEMO_USER = "demo"
DEMO_PASSWORD = "demo-passphrase"  # noqa: S105 - sample data only; refuses to run on a real db


def reset_password(session: Session, username: str) -> None:
    user = session.scalar(select(User).where(User.username == username.lower()))
    if user is None:
        sys.exit(f"No user named {username!r}.")
    password = getpass.getpass("New passphrase (10+ characters): ")
    if len(password) < 10:
        sys.exit("Passphrase must be at least 10 characters.")
    user.password_hash = hash_password(password)
    # Cancels every older route back in. The user makes a new code in Settings.
    user.recovery_code_hash = None
    user.email_hash = None
    session.query(AuthToken).filter(AuthToken.user_id == user.id).delete()
    session.query(AuthSession).filter(AuthSession.user_id == user.id).delete()
    session.commit()
    print(
        f"Passphrase updated for {user.username}. Sessions, recovery code and email were cleared."
    )


def seed_demo(session: Session) -> None:
    if session.scalar(select(User).limit(1)) is not None:
        sys.exit("Refusing to seed: this database already has accounts.")
    rng = random.Random(17)
    now = now_utc()
    days = 60
    start = now - timedelta(days=days)
    user = User(username=DEMO_USER, password_hash=hash_password(DEMO_PASSWORD), created_at=start)
    session.add(user)
    session.flush()

    triggers = ["Stress", "Boredom", "Social", "Routine", "Tired"]
    specs = [
        ("Beer and wine", "alcohol", "reduce", "drink", 2.0, 4.2, 2.0, [18, 19, 20, 21, 22]),
        ("Vape", "nicotine", "reduce", "session", 8.0, 14.0, 6.0, [8, 10, 13, 15, 17, 20]),
    ]
    for name, category, goal, unit, limit, begin, end, hours in specs:
        tracker = Tracker(
            user_id=user.id,
            name=name,
            category=category,
            goal=goal,
            unit=unit,
            default_amount=1,
            daily_limit=limit,
            created_at=start,
        )
        session.add(tracker)
        session.flush()
        if category == "nicotine":
            tracker.baseline_amount, tracker.step_amount, tracker.clear_days = 14.0, 1.0, 7
            tracker.plan_started_on = start.date().isoformat()
            for level in range(7):
                session.add(
                    LimitPeriod(
                        tracker_id=tracker.id,
                        starts_on=(start + timedelta(days=level * 9)).date().isoformat(),
                        goal=goal,
                        daily_limit=14.0 - level,
                    )
                )
        else:
            session.add(
                LimitPeriod(
                    tracker_id=tracker.id,
                    starts_on=start.date().isoformat(),
                    goal=goal,
                    daily_limit=limit,
                )
            )
        for ago in range(days, -1, -1):
            # Sample hours read as the machine's local time, so "evening" looks like evening.
            day = (now - timedelta(days=ago)).astimezone()
            weekend = 1.5 if day.weekday() >= 4 else 0.8
            mean = (begin + (end - begin) * (days - ago) / days) * weekend
            for _ in range(max(0, round(rng.gauss(mean, 1.2)))):
                when = day.replace(hour=rng.choice(hours), minute=rng.randrange(60))
                if when <= now and when >= start:
                    session.add(
                        Entry(
                            tracker_id=tracker.id,
                            kind="use",
                            occurred_at=when,
                            amount=1,
                            craving=rng.randint(2, 9) if rng.random() < 0.5 else None,
                            trigger=rng.choice(triggers) if rng.random() < 0.6 else None,
                        )
                    )
            if rng.random() < 0.5 and start <= day.replace(hour=16) <= now:
                session.add(
                    Entry(
                        tracker_id=tracker.id,
                        kind="urge",
                        occurred_at=day.replace(hour=16),
                        craving=rng.randint(3, 8),
                        trigger=rng.choice(triggers),
                    )
                )
    session.commit()
    print(f"Seeded. Log in as {DEMO_USER} / {DEMO_PASSWORD}")


def backup(source: Path, destination: str) -> None:
    if Path(destination).exists():
        sys.exit(f"{destination} already exists.")
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    Path(destination).chmod(0o600)
    print(f"Backed up to {destination}.")


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "backup":
        backup(load_settings().db_path, args[1])
        return
    if args[:1] == ["seed-demo"] and "TALLY_DB_PATH" not in os.environ:
        sys.exit("Set TALLY_DB_PATH to a throwaway database before seeding.")
    settings = load_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(settings.db_url)
    with Session(make_engine(settings.db_url)) as session:
        if args[:1] == ["seed-demo"]:
            seed_demo(session)
        elif len(args) == 2 and args[0] == "reset-password":
            reset_password(session, args[1])
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    main()
