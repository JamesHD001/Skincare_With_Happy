from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import Order


def cleanup_orphaned_receipts(db, storage, *, older_than_days: int = 7, dry_run: bool = False) -> dict:
    """Delete aged private receipt objects not referenced by any persisted order."""
    if isinstance(older_than_days, bool) or not isinstance(older_than_days, int):
        raise ValueError("older_than_days must be a positive whole number.")
    if older_than_days < 1 or older_than_days > 365:
        raise ValueError("older_than_days must be between 1 and 365.")
    if storage is None or not callable(getattr(storage, "list_receipts", None)):
        raise RuntimeError("Receipt storage does not support safe orphan cleanup.")

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    referenced = set(
        db.session.execute(
            select(Order.receipt_file).where(Order.receipt_file.is_not(None))
        ).scalars()
    )
    candidates = [
        key for key, modified in storage.list_receipts(older_than=cutoff)
        if key not in referenced
    ]
    deleted = []
    if not dry_run:
        try:
            for key in candidates:
                storage.delete(key)
                deleted.append(key)
        except Exception:
            db.session.rollback()
            raise
    return {
        "examined": len(candidates),
        "deleted": len(deleted),
        "dry_run": dry_run,
        "keys": candidates if dry_run else deleted,
    }
