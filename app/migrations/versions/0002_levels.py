"""Limit history, level plans, and client ids that make retried logs safe.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trackers", sa.Column("baseline_amount", sa.Float(), nullable=True))
    op.add_column("trackers", sa.Column("step_amount", sa.Float(), nullable=True))
    op.add_column("trackers", sa.Column("clear_days", sa.Integer(), nullable=True))
    op.add_column("trackers", sa.Column("plan_started_on", sa.String(10), nullable=True))
    op.add_column("entries", sa.Column("client_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_entries_tracker_client", "entries", ["tracker_id", "client_id"], unique=True
    )
    op.create_table(
        "limit_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tracker_id",
            sa.Integer(),
            sa.ForeignKey("trackers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_on", sa.String(10), nullable=False),
        sa.Column("goal", sa.String(10), nullable=False),
        sa.Column("daily_limit", sa.Float(), nullable=True),
        sa.UniqueConstraint("tracker_id", "starts_on", name="uq_limit_periods_tracker_day"),
    )
    # Each existing tracker's current limit becomes its first period.
    op.execute(
        "INSERT INTO limit_periods (tracker_id, starts_on, goal, daily_limit) "
        "SELECT id, substr(created_at, 1, 10), goal, daily_limit FROM trackers"
    )


def downgrade() -> None:
    op.drop_table("limit_periods")
    op.drop_index("ix_entries_tracker_client", table_name="entries")
    with op.batch_alter_table("entries") as batch:
        batch.drop_column("client_id")
    with op.batch_alter_table("trackers") as batch:
        for column in ("plan_started_on", "clear_days", "step_amount", "baseline_amount"):
            batch.drop_column(column)
