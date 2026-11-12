import os
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a fresh disposable PostgreSQL database ending in _test.",
)
class PostgresMigrationTests(unittest.TestCase):
    def test_migrations_upgrade_a_fresh_disposable_database(self):
        database_url = os.environ["TEST_DATABASE_URL"]
        database_name = urlsplit(database_url).path.rstrip("/").rsplit("/", 1)[-1]
        self.assertTrue(
            database_name.lower().endswith("_test"),
            "TEST_DATABASE_URL must target a database whose name ends in _test.",
        )

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            existing_tables = inspect(engine).get_table_names()
        finally:
            engine.dispose()
        self.assertEqual(
            existing_tables,
            [],
            "TEST_DATABASE_URL must point to a fresh database; this test never drops or resets tables.",
        )

        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": database_url,
                "DIRECT_DATABASE_URL": "",
                "APP_ENV": "development",
                "SECRET_KEY": "disposable-migration-test-secret",
            }
        )
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
        self.assertEqual(result.returncode, 0, "Alembic migration failed.")

        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("orders")
                }
        finally:
            engine.dispose()
        self.assertEqual(revision, "20261113_checkout_hardening")
        self.assertIn("inventory_deducted", columns)


if __name__ == "__main__":
    unittest.main()
