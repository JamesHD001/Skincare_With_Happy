"""Add customer authentication token storage.

Revision ID: 20261121_customer_auth_tokens
Revises: 20261120_auth_rate_limits
Create Date: 2026-11-21
"""

from alembic import op
import sqlalchemy as sa

revision = "20261121_customer_auth_tokens"
down_revision = "20261120_auth_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customer_auth_tokens_customer_id", "customer_auth_tokens", ["customer_id"])
    op.create_index("ix_customer_auth_tokens_token_hash", "customer_auth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_customer_auth_tokens_expires_at", "customer_auth_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_customer_auth_tokens_expires_at", table_name="customer_auth_tokens")
    op.drop_index("ix_customer_auth_tokens_token_hash", table_name="customer_auth_tokens")
    op.drop_index("ix_customer_auth_tokens_customer_id", table_name="customer_auth_tokens")
    op.drop_table("customer_auth_tokens")
