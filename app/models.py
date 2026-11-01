from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tracker_id: Mapped[int] = mapped_column(ForeignKey("trackers.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(4))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    amount: Mapped[float | None] = mapped_column(Float)
    craving: Mapped[int | None] = mapped_column(Integer)
    trigger: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(1000))

    tracker: Mapped[Tracker] = relationship(back_populates="entries")
