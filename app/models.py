from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db import UTCDateTime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    recovery_code_hash: Mapped[str | None] = mapped_column(String(255))
    # A keyed hash. The address itself is never stored, so a leaked database has no email list.
    email_hash: Mapped[str | None] = mapped_column(String(64), index=True)


class AuthSession(Base):
    __tablename__ = "sessions"

    # Only a SHA-256 of the cookie token is stored, so a leaked database cannot be replayed.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Tracker(Base):
    __tablename__ = "trackers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(20))
    goal: Mapped[str] = mapped_column(String(10))
    unit: Mapped[str] = mapped_column(String(20))
    default_amount: Mapped[float] = mapped_column(Float)
    daily_limit: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    baseline_amount: Mapped[float | None] = mapped_column(Float)
    step_amount: Mapped[float | None] = mapped_column(Float)
    clear_days: Mapped[int | None] = mapped_column(Integer)
    plan_started_on: Mapped[str | None] = mapped_column(String(10))

    entries: Mapped[list["Entry"]] = relationship(
        back_populates="tracker", cascade="all, delete-orphan", passive_deletes=True
    )


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint("kind IN ('use', 'urge')", name="ck_entries_kind"),
        CheckConstraint(
            "(kind = 'use' AND amount IS NOT NULL) OR (kind = 'urge' AND amount IS NULL)",
            name="ck_entries_amount_matches_kind",
        ),
        CheckConstraint("craving IS NULL OR craving BETWEEN 0 AND 10", name="ck_entries_craving"),
        Index("ix_entries_tracker_occurred", "tracker_id", "occurred_at"),
        Index("ix_entries_tracker_client", "tracker_id", "client_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(4))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    amount: Mapped[float | None] = mapped_column(Float)
    craving: Mapped[int | None] = mapped_column(Integer)
    trigger: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(1000))
    # Set by the device, so resending a log whose reply was lost can't count it twice.
    client_id: Mapped[str | None] = mapped_column(String(64))

    tracker: Mapped[Tracker] = relationship(back_populates="entries")


class LimitPeriod(Base):
    """A goal and limit from a local calendar day on, so changing them can't rewrite the past."""

    __tablename__ = "limit_periods"
    __table_args__ = (
        UniqueConstraint("tracker_id", "starts_on", name="uq_limit_periods_tracker_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id", ondelete="CASCADE"))
    starts_on: Mapped[str] = mapped_column(String(10))
    goal: Mapped[str] = mapped_column(String(10))
    daily_limit: Mapped[float | None] = mapped_column(Float)


class NoUseDay(Base):
    """A finished day confirmed as having no use. A blank day otherwise earns nothing."""

    __tablename__ = "no_use_days"

    tracker_id: Mapped[int] = mapped_column(
        ForeignKey("trackers.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[str] = mapped_column(String(10), primary_key=True)


class AuthToken(Base):
    """A single-use link sent by email. Only a hash is stored."""

    __tablename__ = "auth_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(12))
    email_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
