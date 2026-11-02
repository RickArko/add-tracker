"""Standard drinks: when a tracker began counting them, and what each entry was.

Revision ID: 0006
Revises: 0005

Plain column changes on purpose. A SQLite batch rebuild doesn't keep CHECK constraints it can't
reflect, which would silently drop the ones on entries.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trackers", sa.Column("standard_drinks_from", sa.String(10), nullable=True))
    op.add_column("entries", sa.Column("drink_name", sa.String(60), nullable=True))
    op.add_column("entries", sa.Column("servings", sa.Integer(), nullable=True))
    op.add_column("entries", sa.Column("serving_ml", sa.Float(), nullable=True))
    op.add_column("entries", sa.Column("abv", sa.Float(), nullable=True))


def downgrade() -> None:
    for column in ("abv", "serving_ml", "servings", "drink_name"):
        op.drop_column("entries", column)
    op.drop_column("trackers", "standard_drinks_from")
