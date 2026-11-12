import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_legacy_database(database_path, include_customer_schema, invalid_money=False):
    metadata = MetaData()
    products = Table(
        "products",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(150), nullable=False),
        Column("slug", String(150), nullable=False, unique=True),
        Column("skin_type", String(80), nullable=False),
        Column("price", Float, nullable=False),
        Column("description", Text),
        Column("stock", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    customers = None
    if include_customer_schema:
        customers = Table(
            "customers",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("full_name", String(150), nullable=False),
            Column("email", String(254), nullable=False, unique=True),
            Column("phone_number", String(40)),
            Column("password_hash", String(255), nullable=False),
            Column("created_at", DateTime, nullable=False),
            Column("updated_at", DateTime, nullable=False),
        )
    order_columns = [
        Column("id", Integer, primary_key=True),
    ]
    if include_customer_schema:
        order_columns.append(Column("customer_id", Integer, ForeignKey("customers.id"), nullable=True))
    order_columns.extend(
        [
            Column("customer_name", String(150), nullable=False),
            Column("user_email", String(254 if include_customer_schema else 150), nullable=False),
            Column("phone_number", String(40)),
            Column("total_amount", Float, nullable=False),
            Column("payment_method", String(40), nullable=False),
            Column("payment_status", String(40), nullable=False),
            Column("fulfillment_status", String(40), nullable=False),
            Column("payment_reference", String(120), unique=True),
            Column("receipt_file", String(255)),
            Column("created_at", DateTime, nullable=False),
            Column("updated_at", DateTime, nullable=False),
        ]
    )
    orders = Table("orders", metadata, *order_columns)
    if include_customer_schema:
        from sqlalchemy import Index

        Index("ix_orders_customer_id", orders.c.customer_id)
        admin_profiles = Table(
            "admin_profiles",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("username", String(150), nullable=False, unique=True),
            Column("display_name", String(150), nullable=False),
            Column("email", String(254)),
            Column("phone", String(40)),
            Column("bio", String(500)),
            Column("password_hash", String(255)),
            Column("created_at", DateTime, nullable=False),
            Column("updated_at", DateTime, nullable=False),
        )
    order_items = Table(
        "order_items",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("order_id", Integer, ForeignKey("orders.id"), nullable=False),
        Column("product_id", Integer, ForeignKey("products.id"), nullable=False),
        Column("quantity", Integer, nullable=False),
        Column("unit_price", Float, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    payment_audit_logs = Table(
        "payment_audit_logs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("order_id", Integer, ForeignKey("orders.id"), nullable=False),
        Column("event", String(80), nullable=False),
        Column("details", Text),
        Column("actor", String(100)),
        Column("created_at", DateTime, nullable=False),
    )

    engine = create_engine(URL.create("sqlite", database=str(database_path)))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            metadata.create_all(connection)
            if include_customer_schema:
                connection.execute(
                    customers.insert(),
                    {
                        "id": 4,
                        "full_name": "Legacy Customer",
                        "email": "legacy@example.test",
                        "phone_number": "+2348000000000",
                        "password_hash": "legacy-password-hash",
                        "created_at": datetime(2026, 1, 1),
                        "updated_at": datetime(2026, 1, 1),
                    },
                )
            connection.execute(
                products.insert(),
                {
                    "id": 7,
                    "name": "Legacy Serum",
                    "slug": "legacy-serum",
                    "skin_type": "all",
                    "price": 1.234 if invalid_money else 12.34,
                    "description": "Existing catalog item",
                    "stock": 11,
                    "created_at": datetime(2026, 1, 1),
                },
            )
            order_data = {
                "id": 31,
                "customer_name": "Legacy Buyer",
                "user_email": "legacy@example.test",
                "phone_number": "+2348000000000",
                "total_amount": 24.68,
                "payment_method": "manual_transfer",
                "payment_status": "pending",
                "fulfillment_status": "pending",
                "payment_reference": "LEGACY-31",
                "receipt_file": None,
                "created_at": datetime(2026, 1, 2),
                "updated_at": datetime(2026, 1, 2),
            }
            if include_customer_schema:
                order_data["customer_id"] = 4
            connection.execute(orders.insert(), order_data)
            connection.execute(
                order_items.insert(),
                {
                    "id": 88,
                    "order_id": 31,
                    "product_id": 7,
                    "quantity": 2,
                    "unit_price": 12.34,
                    "created_at": datetime(2026, 1, 2),
                },
            )
            connection.execute(
                payment_audit_logs.insert(),
                {
                    "id": 99,
                    "order_id": 31,
                    "event": "order_created",
                    "details": "Legacy payment audit record",
                    "actor": "customer",
                    "created_at": datetime(2026, 1, 2),
                },
            )
            if include_customer_schema:
                connection.execute(
                    admin_profiles.insert(),
                    {
                        "id": 2,
                        "username": "legacy-admin",
                        "display_name": "Legacy Admin",
                        "email": None,
                        "phone": None,
                        "bio": None,
                        "password_hash": None,
                        "created_at": datetime(2026, 1, 1),
                        "updated_at": datetime(2026, 1, 1),
                    },
                )
    finally:
        engine.dispose()


def run_flask_migration(database_path, *arguments):
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "DATABASE_URL": URL.create("sqlite", database=str(database_path)).render_as_string(),
            "DIRECT_DATABASE_URL": "",
        }
    )
    environment.pop("SECRET_KEY", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "flask",
            "--app",
            "app.app",
            "db",
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class LegacyMigrationTests(unittest.TestCase):
    def test_online_alembic_uses_direct_database_url(self):
        with tempfile.TemporaryDirectory(prefix="skincare-migration-url-") as directory:
            application_path = Path(directory) / "application.sqlite3"
            migration_path = Path(directory) / "migration.sqlite3"
            environment = os.environ.copy()
            environment.update(
                {
                    "APP_ENV": "test",
                    "DATABASE_URL": URL.create(
                        "sqlite", database=str(application_path)
                    ).render_as_string(),
                    "DIRECT_DATABASE_URL": URL.create(
                        "sqlite", database=str(migration_path)
                    ).render_as_string(),
                }
            )
            environment.pop("SECRET_KEY", None)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "flask",
                    "--app",
                    "app.app",
                    "db",
                    "upgrade",
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            application_engine = create_engine(
                URL.create("sqlite", database=str(application_path))
            )
            migration_engine = create_engine(
                URL.create("sqlite", database=str(migration_path))
            )
            try:
                self.assertEqual(inspect(application_engine).get_table_names(), [])
                self.assertIn(
                    "alembic_version",
                    inspect(migration_engine).get_table_names(),
                )
                with migration_engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one(),
                        "20261113_checkout_hardening",
                    )
            finally:
                application_engine.dispose()
                migration_engine.dispose()

    def test_offline_sql_generation_warns_that_money_preflight_is_manual(self):
        environment = os.environ.copy()
        environment.update(
            {
                "APP_ENV": "test",
                "DATABASE_URL": (
                    "postgresql://pooled-user:fake@pooled.invalid/store?sslmode=require"
                ),
                "DIRECT_DATABASE_URL": (
                    "postgresql://migration-user:fake@direct.invalid/store?sslmode=require"
                ),
            }
        )
        environment.pop("SECRET_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flask",
                "--app",
                "app.app",
                "db",
                "upgrade",
                "--sql",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CREATE TABLE customers", result.stdout)
        self.assertIn(
            "Offline SQL generation cannot validate existing money values",
            result.stderr,
        )

    def migrate_temporary_legacy_database(self, include_customer_schema):
        with tempfile.TemporaryDirectory(prefix="skincare-legacy-migration-") as directory:
            database_path = Path(directory) / "legacy.sqlite3"
            create_legacy_database(database_path, include_customer_schema)

            stamped = run_flask_migration(database_path, "stamp", "20261112_initial")
            self.assertEqual(stamped.returncode, 0, stamped.stderr)
            upgraded = run_flask_migration(database_path, "upgrade", "head")
            self.assertEqual(upgraded.returncode, 0, upgraded.stderr)

            engine = create_engine(URL.create("sqlite", database=str(database_path)))
            try:
                inspector = inspect(engine)
                tables = set(inspector.get_table_names())
                self.assertEqual(
                    tables,
                    {
                        "admin_profiles",
                        "alembic_version",
                        "customers",
                        "order_items",
                        "orders",
                        "payment_audit_logs",
                        "products",
                    },
                )
                with engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one(),
                        "20261113_checkout_hardening",
                    )
                    self.assertEqual(
                        connection.execute(
                            text("SELECT name, price FROM products WHERE id=7")
                        ).one(),
                        ("Legacy Serum", 12.34),
                    )
                    order = connection.execute(
                        text(
                            "SELECT customer_id, customer_name, user_email, total_amount, "
                            "payment_reference, inventory_deducted FROM orders WHERE id=31"
                        )
                    ).one()
                    self.assertEqual(order.customer_name, "Legacy Buyer")
                    self.assertEqual(order.user_email, "legacy@example.test")
                    self.assertEqual(str(order.total_amount), "24.68")
                    self.assertEqual(order.payment_reference, "LEGACY-31")
                    self.assertFalse(order.inventory_deducted)
                    self.assertEqual(order.customer_id, 4 if include_customer_schema else None)
                    self.assertEqual(
                        connection.execute(
                            text(
                                "SELECT quantity, unit_price FROM order_items WHERE id=88"
                            )
                        ).one(),
                        (2, 12.34),
                    )
                    self.assertEqual(
                        connection.execute(
                            text("SELECT details FROM payment_audit_logs WHERE id=99")
                        ).scalar_one(),
                        "Legacy payment audit record",
                    )
                    self.assertEqual(
                        connection.execute(text("SELECT count(*) FROM orders")).scalar_one(),
                        1,
                    )
                    self.assertEqual(
                        connection.execute(text("SELECT count(*) FROM products")).scalar_one(),
                        1,
                    )
                    self.assertEqual(
                        connection.execute(text("SELECT count(*) FROM order_items")).scalar_one(),
                        1,
                    )

                customer_columns = {
                    column["name"] for column in inspector.get_columns("customers")
                }
                self.assertTrue(
                    {
                        "full_name",
                        "email",
                        "phone_number",
                        "password_hash",
                        "created_at",
                        "updated_at",
                    }.issubset(customer_columns)
                )
                order_columns = {
                    column["name"]: column
                    for column in inspector.get_columns("orders")
                }
                self.assertEqual(order_columns["user_email"]["type"].length, 254)
                self.assertIn("customer_id", order_columns)
                for table_name, column_name in (
                    ("products", "price"),
                    ("orders", "total_amount"),
                    ("order_items", "unit_price"),
                ):
                    money_type = next(
                        column["type"]
                        for column in inspector.get_columns(table_name)
                        if column["name"] == column_name
                    )
                    self.assertEqual((money_type.precision, money_type.scale), (14, 2))
                order_indexes = {
                    index["name"] for index in inspector.get_indexes("orders")
                }
                self.assertIn("ix_orders_customer_id", order_indexes)
                customer_foreign_keys = inspector.get_foreign_keys("orders")
                self.assertTrue(
                    any(
                        foreign_key["constrained_columns"] == ["customer_id"]
                        and foreign_key["referred_table"] == "customers"
                        for foreign_key in customer_foreign_keys
                    )
                )
                for table_name, unique_column in (
                    ("products", "slug"),
                    ("orders", "payment_reference"),
                    ("customers", "email"),
                ):
                    self.assertTrue(
                        any(
                            constraint["column_names"] == [unique_column]
                            for constraint in inspector.get_unique_constraints(table_name)
                        ),
                        f"Expected unique constraint for {table_name}.{unique_column}",
                    )
                self.assertTrue(
                    any(
                        foreign_key["constrained_columns"] == ["order_id"]
                        and foreign_key["referred_table"] == "orders"
                        for foreign_key in inspector.get_foreign_keys("order_items")
                    )
                )
                self.assertTrue(
                    any(
                        foreign_key["constrained_columns"] == ["product_id"]
                        and foreign_key["referred_table"] == "products"
                        for foreign_key in inspector.get_foreign_keys("order_items")
                    )
                )
                self.assertTrue(
                    any(
                        foreign_key["constrained_columns"] == ["order_id"]
                        and foreign_key["referred_table"] == "orders"
                        for foreign_key in inspector.get_foreign_keys(
                            "payment_audit_logs"
                        )
                    )
                )
            finally:
                engine.dispose()

    def test_initial_baseline_adds_customer_schema_and_preserves_legacy_rows(self):
        self.migrate_temporary_legacy_database(include_customer_schema=False)

    def test_pre_alembic_create_all_schema_is_idempotently_upgraded(self):
        self.migrate_temporary_legacy_database(include_customer_schema=True)

    def test_unrepresentable_money_stops_before_hardening_changes(self):
        with tempfile.TemporaryDirectory(prefix="skincare-legacy-failure-") as directory:
            database_path = Path(directory) / "legacy.sqlite3"
            create_legacy_database(
                database_path,
                include_customer_schema=True,
                invalid_money=True,
            )
            stamped = run_flask_migration(
                database_path,
                "stamp",
                "20261112_customer_accounts",
            )
            self.assertEqual(stamped.returncode, 0, stamped.stderr)

            upgraded = run_flask_migration(database_path, "upgrade", "head")
            self.assertNotEqual(upgraded.returncode, 0)
            self.assertIn("Cannot convert products.price row 7", upgraded.stderr)

            engine = create_engine(URL.create("sqlite", database=str(database_path)))
            try:
                inspector = inspect(engine)
                columns = {
                    column["name"]
                    for column in inspector.get_columns("orders")
                }
                self.assertNotIn("inventory_deducted", columns)
                price_type = next(
                    column["type"]
                    for column in inspector.get_columns("products")
                    if column["name"] == "price"
                )
                self.assertIsInstance(price_type, Float)
                with engine.connect() as connection:
                    self.assertEqual(
                        connection.execute(
                            text("SELECT version_num FROM alembic_version")
                        ).scalar_one(),
                        "20261112_customer_accounts",
                    )
                    self.assertEqual(
                        connection.execute(
                            text("SELECT price FROM products WHERE id=7")
                        ).scalar_one(),
                        1.234,
                    )
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
