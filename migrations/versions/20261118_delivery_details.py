"""Add saved customer delivery details and immutable order snapshots.

Revision ID: 20261118_delivery_details
Revises: 20261114_product_images
Create Date: 2026-11-18
"""

from alembic import op
import sqlalchemy as sa


revision = "20261118_delivery_details"
down_revision = "20261114_product_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    customer_columns = (
        ("delivery_state", sa.String(length=100)),
        ("delivery_city", sa.String(length=120)),
        ("delivery_address", sa.String(length=500)),
        ("delivery_landmark", sa.String(length=250)),
    )
    order_columns = (
        ("delivery_recipient_name", sa.String(length=150)),
        ("delivery_phone", sa.String(length=40)),
        ("delivery_email", sa.String(length=254)),
        ("delivery_state", sa.String(length=100)),
        ("delivery_city", sa.String(length=120)),
        ("delivery_address", sa.String(length=500)),
        ("delivery_landmark", sa.String(length=250)),
    )
    for name, column_type in customer_columns:
        op.add_column("customers", sa.Column(name, column_type, nullable=True))
    for name, column_type in order_columns:
        op.add_column("orders", sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for name in (
        "delivery_landmark",
        "delivery_address",
        "delivery_city",
        "delivery_state",
        "delivery_email",
        "delivery_phone",
        "delivery_recipient_name",
    ):
        op.drop_column("orders", name)
    for name in (
        "delivery_landmark",
        "delivery_address",
        "delivery_city",
        "delivery_state",
    ):
        op.drop_column("customers", name)
