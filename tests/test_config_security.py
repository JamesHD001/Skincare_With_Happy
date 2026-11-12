import os
import secrets
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy.engine import make_url

os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "configuration-test-secret"

from app.config import normalize_postgres_url, select_migration_database_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config_in_isolated_process(app_env, secret_key=None):
    environment = os.environ.copy()
    environment["APP_ENV"] = app_env
    environment["DATABASE_URL"] = "sqlite:///:memory:"
    environment["DIRECT_DATABASE_URL"] = ""
    environment.pop("SECRET_KEY", None)
    if secret_key is not None:
        environment["SECRET_KEY"] = secret_key
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, types; "
            "sys.modules['dotenv'] = types.SimpleNamespace("
            "load_dotenv=lambda *args, **kwargs: None); "
            "from app.app import create_app; create_app()",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class ConfigurationSecurityTests(unittest.TestCase):
    def test_production_requires_secret_key(self):
        result = load_config_in_isolated_process("production")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production requires SECRET_KEY", result.stderr)

    def test_production_accepts_a_unique_long_secret_without_logging_it(self):
        secret_key = secrets.token_urlsafe(32)
        result = load_config_in_isolated_process("production", secret_key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(secret_key, result.stdout + result.stderr)

    def test_production_rejects_known_insecure_secret_without_echoing_value(self):
        for secret_key in (
            "skincare-with-happy-dev-secret",
            "skincare-with-happy-development-only-secret",
            "skincare-with-happy-test-only-secret",
        ):
            with self.subTest(secret_key=secret_key):
                result = load_config_in_isolated_process("production", secret_key)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("production SECRET_KEY is insecure", result.stderr)
                self.assertNotIn(secret_key, result.stdout + result.stderr)

    def test_development_and_test_have_environment_specific_fallbacks(self):
        for app_env, expected in (
            ("development", "skincare-with-happy-development-only-secret"),
            ("test", "skincare-with-happy-test-only-secret"),
        ):
            with self.subTest(app_env=app_env):
                environment = os.environ.copy()
                environment["APP_ENV"] = app_env
                environment.pop("SECRET_KEY", None)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "import sys, types; "
                        "sys.modules['dotenv'] = types.SimpleNamespace("
                        "load_dotenv=lambda *args, **kwargs: None); "
                        "from app.config import SECRET_KEY; "
                        "assert SECRET_KEY == __import__('os').environ['EXPECTED_KEY']",
                    ],
                    cwd=PROJECT_ROOT,
                    env={**environment, "EXPECTED_KEY": expected},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_test_environment_does_not_load_project_dotenv(self):
        environment = os.environ.copy()
        environment["APP_ENV"] = "test"
        environment.pop("SECRET_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.config import SECRET_KEY; "
                "assert SECRET_KEY == 'skincare-with-happy-test-only-secret'",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_postgres_urls_use_psycopg_and_preserve_query_parameters(self):
        for raw_url in (
            "postgres://user:password@db.example.test/store?sslmode=require&application_name=test",
            "postgresql://user:password@db.example.test/store?sslmode=require",
            "postgresql+psycopg2://user:password@db.example.test/store?sslmode=require",
        ):
            with self.subTest(raw_url=raw_url):
                normalized = normalize_postgres_url(raw_url)
                parsed = make_url(normalized)
                self.assertEqual(parsed.drivername, "postgresql+psycopg")
                self.assertEqual(parsed.query["sslmode"], "require")
                if "application_name=test" in raw_url:
                    self.assertEqual(parsed.query["application_name"], "test")

    def test_migration_url_prefers_direct_and_falls_back_to_application_url(self):
        direct_url = "postgresql+psycopg://migration.example.test/db"
        pooled_url = "postgresql+psycopg://pooled.example.test/db"
        self.assertEqual(
            select_migration_database_url(direct_url, pooled_url),
            direct_url,
        )
        self.assertEqual(
            select_migration_database_url(None, pooled_url),
            pooled_url,
        )


if __name__ == "__main__":
    unittest.main()
