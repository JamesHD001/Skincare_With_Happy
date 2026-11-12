import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load only the project-root .env in non-test environments.
if os.getenv("APP_ENV", "").strip().lower() != "test":
    load_dotenv(ENV_FILE, override=False)


def _read_setting(*names, default=""):
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


PAYSTACK_PUBLIC_KEY = _read_setting("PAYSTACK_PUBLIC_KEY")
PAYSTACK_SECRET_KEY = _read_setting("PAYSTACK_SECRET_KEY")
ADMIN_USERNAME = _read_setting("ADMIN_USERNAME")
ADMIN_PASSWORD = _read_setting("ADMIN_PASSWORD")
RECEIPT_STORAGE_BUCKET = _read_setting("RECEIPT_STORAGE_BUCKET")
RECEIPT_STORAGE_REGION = _read_setting("RECEIPT_STORAGE_REGION")
RECEIPT_STORAGE_ENDPOINT_URL = _read_setting("RECEIPT_STORAGE_ENDPOINT_URL")
RECEIPT_STORAGE_ACCESS_KEY_ID = _read_setting("RECEIPT_STORAGE_ACCESS_KEY_ID")
RECEIPT_STORAGE_SECRET_ACCESS_KEY = _read_setting("RECEIPT_STORAGE_SECRET_ACCESS_KEY")
MAX_RECEIPT_SIZE_BYTES = 5 * 1024 * 1024


def normalize_postgres_url(url):
    if not url:
        return url
    parsed_url = make_url(url)
    if parsed_url.drivername in {
        "postgres",
        "postgresql",
        "postgresql+psycopg2",
    }:
        parsed_url = parsed_url.set(drivername="postgresql+psycopg")
    return parsed_url.render_as_string(hide_password=False)


def select_migration_database_url(direct_url, application_url):
    return direct_url or application_url


# DATABASE_URL uses the pooled connection string for application traffic.
# DIRECT_DATABASE_URL is preferred for migrations; DATABASE_URL is the explicit
# fallback when no direct connection string is configured.
DATABASE_URL = normalize_postgres_url(_read_setting("DATABASE_URL"))
DIRECT_DATABASE_URL = normalize_postgres_url(_read_setting("DIRECT_DATABASE_URL"))

# The application gracefully falls back to SQLite for local development if the
# PostgreSQL environment variables are not defined yet.
SQLITE_DATABASE_PATH = _read_setting("SQLITE_DATABASE_PATH", default="database.db")
raw_database_url = DATABASE_URL or DIRECT_DATABASE_URL or f"sqlite:///{SQLITE_DATABASE_PATH}"
SQLALCHEMY_DATABASE_URI = raw_database_url
MIGRATION_DATABASE_URL = select_migration_database_url(
    DIRECT_DATABASE_URL,
    SQLALCHEMY_DATABASE_URI,
)

# Keep the legacy SQLite path available for existing scripts and local debugging.
DATABASE = SQLITE_DATABASE_PATH

APP_ENV = _read_setting("APP_ENV", default="development").lower()

_INSECURE_SECRET_KEYS = {
    "change-me",
    "changeme",
    "development",
    "secret",
    "skincare-with-happy-development-only-secret",
    "skincare-with-happy-dev-secret",
    "skincare-with-happy-test-only-secret",
    "your-secret-key",
}
_DEVELOPMENT_SECRET_KEY = "skincare-with-happy-development-only-secret"
_TEST_SECRET_KEY = "skincare-with-happy-test-only-secret"


def _configured_secret_key():
    secret_key = _read_setting("SECRET_KEY")
    if APP_ENV == "production":
        if not secret_key:
            raise RuntimeError(
                "Production requires SECRET_KEY. Configure a unique random value "
                "of at least 32 characters in the deployment environment."
            )
        if (
            len(secret_key.encode("utf-8")) < 32
            or secret_key.lower() in _INSECURE_SECRET_KEYS
            or len(set(secret_key)) < 8
        ):
            raise RuntimeError(
                "The production SECRET_KEY is insecure. Configure a unique random "
                "value of at least 32 characters; do not use a development/default value."
            )
        return secret_key
    if secret_key:
        return secret_key
    return _TEST_SECRET_KEY if APP_ENV == "test" else _DEVELOPMENT_SECRET_KEY


SECRET_KEY = _configured_secret_key()
PORT = int(_read_setting("PORT", default="5000"))
DEBUG = APP_ENV != "production"
