"""Initial schema.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(40), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "trackers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("goal", sa.String(10), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("default_amount", sa.Float(), nullable=False),
        sa.Column("daily_limit", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_trackers_user_id", "trackers", ["user_id"])
    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tracker_id",
            sa.Integer(),
            sa.ForeignKey("trackers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(4), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("craving", sa.Integer(), nullable=True),
        sa.Column("trigger", sa.String(40), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.CheckConstraint("kind IN ('use', 'urge')", name="ck_entries_kind"),
        sa.CheckConstraint(
            "(kind = 'use' AND amount IS NOT NULL) OR (kind = 'urge' AND amount IS NULL)",
            name="ck_entries_amount_matches_kind",
        ),
        sa.CheckConstraint(
            "craving IS NULL OR craving BETWEEN 0 AND 10", name="ck_entries_craving"
        ),
    )
    op.create_index("ix_entries_tracker_occurred", "entries", ["tracker_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("entries")
    op.drop_table("trackers")
    op.drop_table("sessions")
    op.drop_table("users")
