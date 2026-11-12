import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Load only the project-root .env; .env.example is a template and is never read.
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

# Neon PostgreSQL configuration.
# DATABASE_URL uses the pooled connection string for app traffic.
# DIRECT_DATABASE_URL is reserved for migrations and admin tasks.
def _normalize_postgres_url(url):
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_postgres_url(_read_setting("DATABASE_URL"))
DIRECT_DATABASE_URL = _normalize_postgres_url(_read_setting("DIRECT_DATABASE_URL"))

# The application gracefully falls back to SQLite for local development if the
# PostgreSQL environment variables are not defined yet.
SQLITE_DATABASE_PATH = _read_setting("SQLITE_DATABASE_PATH", default="database.db")
raw_database_url = DATABASE_URL or DIRECT_DATABASE_URL or f"sqlite:///{SQLITE_DATABASE_PATH}"
SQLALCHEMY_DATABASE_URI = raw_database_url

# Keep the legacy SQLite path available for existing scripts and local debugging.
DATABASE = SQLITE_DATABASE_PATH

# Configure a stable secret in the local .env and hosting environment before deployment.
SECRET_KEY = _read_setting("SECRET_KEY", default="skincare-with-happy-dev-secret")

APP_ENV = _read_setting("APP_ENV", default="development").lower()
PORT = int(_read_setting("PORT", default="5000"))
DEBUG = APP_ENV != "production"
