"""Initial database schema for skincare storefront.

Revision ID: 20261112_initial
Revises: 
Create Date: 2026-11-12 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20261112_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=150), nullable=False),
        sa.Column("skin_type", sa.String(length=80), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=150), nullable=False),
        sa.Column("user_email", sa.String(length=150), nullable=False),
        sa.Column("phone_number", sa.String(length=40), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("payment_method", sa.String(length=40), nullable=False),
        sa.Column("payment_status", sa.String(length=40), nullable=False),
        sa.Column("fulfillment_status", sa.String(length=40), nullable=False),
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
        sa.Column("receipt_file", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference"),
    )
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "payment_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=80), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("payment_audit_logs")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
