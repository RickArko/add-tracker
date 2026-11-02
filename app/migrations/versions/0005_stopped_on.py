"""The last day of use, for someone who had already stopped when they started tracking.

Revision ID: 0005
Revises: 0003

Branches from 0003 so it doesn't depend on the recovery migration on the auth-methods branch.
They touch different things, so either can run first, and startup upgrades to every head.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trackers", sa.Column("stopped_on", sa.String(10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trackers") as batch:
        batch.drop_column("stopped_on")
