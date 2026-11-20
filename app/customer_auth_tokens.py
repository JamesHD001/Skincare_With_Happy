"""Single-use customer verification and password-reset token lifecycle."""

import hashlib
import secrets
from datetime import datetime, timedelta

from app.models import CustomerAuthToken

PURPOSES = {"email_verification", "password_reset"}


def issue_customer_token(db, customer, *, purpose, lifetime_minutes=30, now=None):
    """Create a high-entropy token; persist only its SHA-256 digest."""
    if purpose not in PURPOSES:
        raise ValueError("Unsupported customer token purpose.")
    if not isinstance(lifetime_minutes, int) or isinstance(lifetime_minutes, bool) or not 1 <= lifetime_minutes <= 1440:
        raise ValueError("Token lifetime must be between 1 and 1440 minutes.")

    issued_at = now or datetime.utcnow()
    raw_token = secrets.token_urlsafe(32)
    record = CustomerAuthToken(
        customer_id=customer.id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        purpose=purpose,
        expires_at=issued_at + timedelta(minutes=lifetime_minutes),
    )
    db.session.add(record)
    db.session.commit()
    return raw_token


def consume_customer_token(db, raw_token, *, purpose, now=None):
    """Consume a valid token once and return its customer, otherwise return None."""
    if purpose not in PURPOSES or not isinstance(raw_token, str) or not raw_token:
        return None

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    current_time = now or datetime.utcnow()
    try:
        record = (
            db.session.query(CustomerAuthToken)
            .filter_by(token_hash=token_hash, purpose=purpose)
            .with_for_update()
            .first()
        )
        if record is None or record.used_at is not None or record.expires_at <= current_time:
            db.session.rollback()
            return None

        record.used_at = current_time
        customer = record.customer
        db.session.commit()
        return customer
    except Exception:
        db.session.rollback()
        raise


def invalidate_customer_tokens(db, customer, *, purpose, now=None):
    """Invalidate all outstanding tokens for one customer and purpose."""
    if purpose not in PURPOSES:
        raise ValueError("Unsupported customer token purpose.")
    current_time = now or datetime.utcnow()
    updated = (
        db.session.query(CustomerAuthToken)
        .filter_by(customer_id=customer.id, purpose=purpose, used_at=None)
        .update({CustomerAuthToken.used_at: current_time}, synchronize_session=False)
    )
    db.session.commit()
    return updated
