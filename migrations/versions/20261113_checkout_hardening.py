"""Use fixed-precision money and track inventory reservations.

Revision ID: 20261113_checkout_hardening
Revises: 20261112_customer_accounts
Create Date: 2026-11-13
"""

from decimal import Decimal, InvalidOperation
import logging

from alembic import op
import sqlalchemy as sa


revision = "20261113_checkout_hardening"
down_revision = "20261112_customer_accounts"
branch_labels = None
depends_on = None

MAX_AMOUNT = Decimal("1000000000000")
MONEY_COLUMNS = (
    ("products", "price"),
    ("orders", "total_amount"),
    ("order_items", "unit_price"),
)


def _validate_money_precision() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column in MONEY_COLUMNS:
        if not inspector.has_table(table):
            continue
        rows = bind.execute(sa.text(f"SELECT id, {column} FROM {table}"))
        for row_id, raw_value in rows:
            try:
                value = Decimal(str(raw_value))
                if not value.is_finite() or abs(value) >= MAX_AMOUNT:
                    raise InvalidOperation
                if value != value.quantize(Decimal("0.01")):
                    raise InvalidOperation
            except (InvalidOperation, TypeError, ValueError):
                message = (
                    f"Cannot convert {table}.{column} row {row_id} to Numeric(14, 2): "
                    "the value is non-finite, has more than two decimal places, or "
                    "exceeds the supported range. Reconcile this row manually, then "
                    "rerun the migration."
                )
                logging.getLogger("alembic.runtime.migration").error(message)
                raise RuntimeError(message) from None


def upgrade() -> None:
    if op.get_context().as_sql:
        logging.getLogger("alembic.runtime.migration").warning(
            "Offline SQL generation cannot validate existing money values; "
            "run the checkout-hardening data preflight on the target database "
            "before applying this SQL."
        )
    else:
        _validate_money_precision()

    for table, column in MONEY_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.Float(),
                type_=sa.Numeric(14, 2),
                existing_nullable=False,
            )

    offline_mode = op.get_context().as_sql
    inspector = None if offline_mode else sa.inspect(op.get_bind())
    order_columns = (
        set()
        if offline_mode
        else {column["name"] for column in inspector.get_columns("orders")}
    )
    if offline_mode or "inventory_deducted" not in order_columns:
        with op.batch_alter_table("orders") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "inventory_deducted",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("orders"):
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        if "inventory_deducted" in order_columns:
            with op.batch_alter_table("orders") as batch_op:
                batch_op.drop_column("inventory_deducted")

    for table, column in reversed(MONEY_COLUMNS):
        if sa.inspect(op.get_bind()).has_table(table):
            with op.batch_alter_table(table) as batch_op:
                batch_op.alter_column(
                    column,
                    existing_type=sa.Numeric(14, 2),
                    type_=sa.Float(),
                    existing_nullable=False,
                )
