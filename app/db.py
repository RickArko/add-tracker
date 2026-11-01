"""Engine setup, schema migration, and the UTC datetime column type."""

from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.types import TypeDecorator

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class UTCDateTime(TypeDecorator):
    """Stores aware datetimes as naive UTC; always returns aware UTC.

    SQLite has no timezone support, so this keeps every timestamp comparable.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=UTC)


def now_utc() -> datetime:
    return datetime.now(UTC)


def make_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _configure_sqlite(conn, _record):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        # Deleted rows are overwritten rather than left readable in free pages.
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.close()

    return engine


def run_migrations(db_url: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["db_url"] = db_url
    command.upgrade(config, "heads")
