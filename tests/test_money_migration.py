import importlib.util
import unittest
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20261113_checkout_hardening.py"
)
spec = importlib.util.spec_from_file_location("checkout_hardening_migration", MIGRATION_PATH)
checkout_migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkout_migration)


class MoneyMigrationPreflightTests(unittest.TestCase):
    def run_preflight(self, rows):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                for table, column, value in rows:
                    connection.execute(
                        text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {column} FLOAT NOT NULL)")
                    )
                    connection.execute(
                        text(f"INSERT INTO {table} (id, {column}) VALUES (1, :value)"),
                        {"value": value},
                    )
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    checkout_migration._validate_money_precision()
        finally:
            engine.dispose()

    def test_preflight_accepts_existing_exact_cent_values(self):
        self.run_preflight(
            [
                ("products", "price", 30.0),
                ("orders", "total_amount", 123.45),
                ("order_items", "unit_price", 18.0),
            ]
        )

    def test_preflight_rejects_unrepresentable_amounts_before_conversion(self):
        for table, column, value in (
            ("products", "price", 1.234),
            ("orders", "total_amount", 1000000000000),
            ("order_items", "unit_price", float("inf")),
        ):
            with self.subTest(table=table, value=value):
                with self.assertRaisesRegex(
                    RuntimeError, rf"Cannot convert {table}\.{column} row 1"
                ):
                    self.run_preflight([(table, column, value)])


if __name__ == "__main__":
    unittest.main()
