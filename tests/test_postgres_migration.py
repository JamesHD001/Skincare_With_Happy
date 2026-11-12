import os
import re
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "postgres-migration-test-secret"

from app.config import normalize_postgres_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_POSTGRES_MIGRATION_TESTS = os.environ.get(
    "RUN_POSTGRES_MIGRATION_TESTS", ""
).strip().lower() in {"1", "true", "yes"}


def points_to_same_database(first_url, second_url):
    first = make_url(first_url)
    second = make_url(second_url)
    return (
        (first.host or "").lower().replace("-pooler.", "."),
        first.port,
        first.database,
    ) == (
        (second.host or "").lower().replace("-pooler.", "."),
        second.port,
        second.database,
    )


class PostgresMigrationTests(unittest.TestCase):
    def test_pooler_and_direct_hosts_for_the_same_database_are_detected(self):
        pooled_url = "postgresql+psycopg://user:test-only@ep-example-pooler.region.neon.tech/store_test"
        direct_url = "postgresql+psycopg://user:test-only@ep-example.region.neon.tech/store_test"
        self.assertTrue(points_to_same_database(pooled_url, direct_url))

    def test_explicit_opt_in_without_database_url_fails_clearly(self):
        environment = os.environ.copy()
        environment["RUN_POSTGRES_MIGRATION_TESTS"] = "1"
        environment["APP_ENV"] = "test"
        environment["TEST_DATABASE_URL"] = ""
        environment.pop("SECRET_KEY", None)
        environment["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (str(PROJECT_ROOT), environment.get("PYTHONPATH", ""))
            if value
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "test_postgres_migration.PostgresMigrationTests."
                "test_migrations_upgrade_a_fresh_disposable_schema",
            ],
            cwd=PROJECT_ROOT / "tests",
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RUN_POSTGRES_MIGRATION_TESTS=1 requires TEST_DATABASE_URL", result.stderr)

    def test_migrations_upgrade_a_fresh_disposable_schema(self):
        if not RUN_POSTGRES_MIGRATION_TESTS:
            self.skipTest(
                "Set RUN_POSTGRES_MIGRATION_TESTS=1 and TEST_DATABASE_URL to run "
                "the disposable PostgreSQL migration test."
            )
        raw_test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
        if not raw_test_url:
            self.fail(
                "RUN_POSTGRES_MIGRATION_TESTS=1 requires TEST_DATABASE_URL."
            )
        try:
            test_url = make_url(normalize_postgres_url(raw_test_url))
        except (ArgumentError, TypeError, ValueError):
            self.fail("TEST_DATABASE_URL must be a valid PostgreSQL SQLAlchemy URL.")
        if test_url.drivername != "postgresql+psycopg":
            self.fail("TEST_DATABASE_URL must use the Psycopg 3 PostgreSQL driver.")
        if not (test_url.database or "").lower().endswith("_test"):
            self.fail("TEST_DATABASE_URL must target a database whose name ends in _test.")

        for application_variable in ("DATABASE_URL", "DIRECT_DATABASE_URL"):
            application_url = os.environ.get(application_variable, "").strip()
            if not application_url:
                continue
            try:
                normalized_application_url = normalize_postgres_url(application_url)
                if points_to_same_database(
                    test_url.render_as_string(hide_password=False),
                    normalized_application_url,
                ):
                    self.fail(
                        "TEST_DATABASE_URL must not point to the application database."
                    )
            except (ArgumentError, TypeError, ValueError):
                continue

        schema_name = f"migration_test_{uuid.uuid4().hex}"
        base_url = test_url
        base_engine = create_engine(base_url, pool_pre_ping=True)
        schema_created = False
        try:
            try:
                with base_engine.begin() as connection:
                    actual_database = connection.execute(
                        text("SELECT current_database()")
                    ).scalar_one()
                    if not actual_database.lower().endswith("_test"):
                        self.fail(
                            "TEST_DATABASE_URL resolved to a database not ending in _test."
                        )
                    connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
                    schema_created = True
            except SQLAlchemyError as error:
                self.fail(
                    "Unable to create an isolated schema in TEST_DATABASE_URL "
                    f"({type(error).__name__}). Check that the disposable database "
                    "is reachable and the test role can create schemas."
                )
        finally:
            base_engine.dispose()

        query = dict(base_url.query)
        existing_options = str(query.get("options", "")).strip()
        query["options"] = f"{existing_options} -csearch_path={schema_name}".strip()
        schema_url = base_url.set(query=query)
        environment = os.environ.copy()
        environment.update(
            {
                "DATABASE_URL": schema_url.render_as_string(hide_password=False),
                "DIRECT_DATABASE_URL": schema_url.render_as_string(hide_password=False),
                "APP_ENV": "test",
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
        redacted_stderr = re.sub(
            r"(?i)(?:postgres|postgresql)(?:\+\w+)?://\S+",
            "[redacted PostgreSQL URL]",
            result.stderr,
        )
        try:
            self.assertEqual(
                result.returncode,
                0,
                f"Alembic migration failed in the isolated test schema:\n{redacted_stderr}",
            )
            verification_url = schema_url
            engine = create_engine(verification_url, pool_pre_ping=True)
            try:
                with engine.connect() as connection:
                    revision = connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar_one()
                    columns = {
                        column["name"]
                        for column in inspect(connection).get_columns("orders")
                    }
                self.assertEqual(revision, "20261113_checkout_hardening")
                self.assertIn("inventory_deducted", columns)
                self.assertCountEqual(
                    inspect(engine).get_table_names(),
                    [
                        "admin_profiles",
                        "alembic_version",
                        "customers",
                        "order_items",
                        "orders",
                        "payment_audit_logs",
                        "products",
                    ],
                )
            finally:
                engine.dispose()
        finally:
            if schema_created:
                cleanup_engine = create_engine(base_url, pool_pre_ping=True)
                try:
                    with cleanup_engine.begin() as connection:
                        connection.execute(
                            text(f'DROP SCHEMA "{schema_name}" CASCADE')
                        )
                finally:
                    cleanup_engine.dispose()


if __name__ == "__main__":
    unittest.main()
