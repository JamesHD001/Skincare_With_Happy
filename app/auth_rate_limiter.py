"""Shared-database, privacy-preserving rate limits for customer authentication."""

import hashlib
import hmac
from datetime import datetime, timedelta

from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import AuthRateLimit


def hashed_rate_limit_keys(secret_key, endpoint, ip_address, email):
    """Return opaque per-IP and per-IP/email keys; raw identifiers are never stored."""
    prefix = f"{endpoint.strip()}\0"
    ip_digest = hmac.new(
        secret_key.encode("utf-8"),
        f"{prefix}ip\0{ip_address}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    identity_digest = hmac.new(
        secret_key.encode("utf-8"),
        f"{prefix}identity\0{ip_address}\0{email}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"ip": ip_digest, "email": identity_digest}


def consume_auth_attempts(db, keys, *, email_limit, ip_limit, window_seconds):
    """Atomically increment both buckets in one transaction; fail closed on DB errors."""
    if window_seconds < 1 or email_limit < 1 or ip_limit < 1:
        raise ValueError("Rate-limit settings must be positive integers.")

    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    table = AuthRateLimit.__table__
    insert_factory = {
        "postgresql": pg_insert,
        "sqlite": sqlite_insert,
    }.get(db.engine.dialect.name)
    if insert_factory is None:
        raise RuntimeError("The configured database does not support atomic rate-limit upserts.")

    counts = {}
    try:
        for bucket, limit in (("email", email_limit), ("ip", ip_limit)):
            key_hash = keys[bucket]
            statement = insert_factory(table).values(
                key_hash=key_hash,
                window_started_at=now,
                attempts=1,
            )
            expired = table.c.window_started_at <= cutoff
            statement = statement.on_conflict_do_update(
                index_elements=[table.c.key_hash],
                set_={
                    "window_started_at": case((expired, now), else_=table.c.window_started_at),
                    "attempts": case((expired, 1), else_=table.c.attempts + 1),
                },
            ).returning(table.c.attempts)
            counts[bucket] = db.session.execute(statement).scalar_one()
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    allowed = counts["email"] <= email_limit and counts["ip"] <= ip_limit
    return allowed, window_seconds


def purge_expired_auth_limits(db, *, older_than_hours=24):
    if older_than_hours < 1:
        raise ValueError("Retention must be at least one hour.")
    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
    result = db.session.execute(
        delete(AuthRateLimit).where(AuthRateLimit.window_started_at < cutoff)
    )
    db.session.commit()
    return result.rowcount or 0
