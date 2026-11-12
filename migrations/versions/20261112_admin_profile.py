"""Add persistent admin profiles and password hashes.

Revision ID: 20261112_admin_profile
Revises: 20261112_initial
Create Date: 2026-11-12 17:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261112_admin_profile"
down_revision = "20261112_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline_mode = op.get_context().as_sql
    if offline_mode or not sa.inspect(op.get_bind()).has_table("admin_profiles"):
        op.create_table(
            "admin_profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=150), nullable=False),
            sa.Column("display_name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=True),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("bio", sa.String(length=500), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("admin_profiles"):
        op.drop_table("admin_profiles")
