from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


def get_database_url() -> str:
    url = os.getenv("DIRECT_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DIRECT_DATABASE_URL or DATABASE_URL is not configured.")
    return url


def build_dump_command(database_url: str, destination: Path) -> list[str]:
    # The app uses a Neon PostgreSQL database, so pg_dump is the safest standard export format.
    return [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "--file",
        str(destination),
        database_url,
    ]


def main() -> int:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dump_path = BACKUP_DIR / f"skincare_with_happy_{timestamp}.sql"
    database_url = get_database_url()

    print(f"Starting Neon backup to {dump_path}")
    subprocess.run(build_dump_command(database_url, dump_path), check=True)
    print(f"Backup complete: {dump_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
