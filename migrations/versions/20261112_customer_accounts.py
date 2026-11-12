"""Add customer accounts and optional order ownership.

Revision ID: 20261112_customer_accounts
Revises: 20261112_admin_profile
Create Date: 2026-11-12 17:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261112_customer_accounts"
down_revision = "20261112_admin_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("customers"):
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("full_name", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("phone_number", sa.String(length=40), nullable=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )

    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    if "customer_id" not in order_columns:
        with op.batch_alter_table("orders") as batch_op:
            batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_orders_customer_id_customers",
                "customers",
                ["customer_id"],
                ["id"],
            )

    order_indexes = {index["name"] for index in inspector.get_indexes("orders")}
    if "ix_orders_customer_id" not in order_indexes:
        op.create_index("ix_orders_customer_id", "orders", ["customer_id"])

    user_email = next(column for column in inspector.get_columns("orders") if column["name"] == "user_email")
    if getattr(user_email["type"], "length", None) != 254:
        with op.batch_alter_table("orders") as batch_op:
            batch_op.alter_column(
                "user_email",
                existing_type=sa.String(length=150),
                type_=sa.String(length=254),
                existing_nullable=False,
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("orders"):
        order_indexes = {index["name"] for index in inspector.get_indexes("orders")}
        if "ix_orders_customer_id" in order_indexes:
            op.drop_index("ix_orders_customer_id", table_name="orders")
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        if "customer_id" in order_columns:
            with op.batch_alter_table("orders") as batch_op:
                batch_op.drop_constraint("fk_orders_customer_id_customers", type_="foreignkey")
                batch_op.drop_column("customer_id")
        user_email = next(column for column in inspector.get_columns("orders") if column["name"] == "user_email")
        if getattr(user_email["type"], "length", None) == 254:
            with op.batch_alter_table("orders") as batch_op:
                batch_op.alter_column(
                    "user_email",
                    existing_type=sa.String(length=254),
                    type_=sa.String(length=150),
                    existing_nullable=False,
                )
    if inspector.has_table("customers"):
        op.drop_table("customers")
