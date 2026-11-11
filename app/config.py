import os

from dotenv import load_dotenv

# Load local environment variables before reading application configuration.
load_dotenv()

PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY", "")
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")

# Neon PostgreSQL configuration.
# DATABASE_URL should use Neon's pooled connection string for normal app traffic.
# DIRECT_DATABASE_URL is reserved for schema migrations and administrative tasks.
DATABASE_URL = os.getenv("DATABASE_URL", "")
DIRECT_DATABASE_URL = os.getenv("DIRECT_DATABASE_URL", "")

# SQLAlchemy can use this URI once the application is migrated from sqlite3.
# The current application routes still use the legacy SQLite helper in app.py.
SQLALCHEMY_DATABASE_URI = DATABASE_URL or "sqlite:///database.db"

# Keep the existing SQLite path available during the staged database migration.
DATABASE = os.getenv("SQLITE_DATABASE_PATH", "database.db")

# Configure a stable secret in the local .env and hosting environment before deployment.
SECRET_KEY = os.getenv("SECRET_KEY") or os.urandom(24)
