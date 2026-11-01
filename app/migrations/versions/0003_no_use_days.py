"""Days someone confirmed as having no use.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "no_use_days",
        sa.Column(
            "tracker_id",
            sa.Integer(),
            sa.ForeignKey("trackers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day", sa.String(10), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("no_use_days")
