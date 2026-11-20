"""Add shared authentication rate-limit storage.

Revision ID: 20261120_auth_rate_limits
Revises: 20261118_delivery_details
Create Date: 2026-11-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261120_auth_rate_limits"
down_revision = "20261118_delivery_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_rate_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("key_hash", name="uq_auth_rate_limits_key_hash"),
    )
    op.create_index("ix_auth_rate_limits_key_hash", "auth_rate_limits", ["key_hash"])


def downgrade() -> None:
    op.drop_index("ix_auth_rate_limits_key_hash", table_name="auth_rate_limits")
    op.drop_table("auth_rate_limits")
