"""Recovery codes, optional keyed email hash, and single-use email tokens.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("recovery_code_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("email_hash", sa.String(64), nullable=True))
    op.create_index("ix_users_email_hash", "users", ["email_hash"])
    op.create_table(
        "auth_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("purpose", sa.String(12), nullable=False),
        sa.Column("email_hash", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("auth_tokens")
    op.drop_index("ix_users_email_hash", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_hash")
        batch.drop_column("recovery_code_hash")
