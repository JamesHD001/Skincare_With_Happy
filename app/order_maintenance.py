from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.models import Order, OrderItem, PaymentAuditLog, Product


def expire_unverified_orders(db, *, older_than_hours: int = 48, dry_run: bool = False) -> dict:
    """Expire stale unverified orders and release their reserved inventory once.

    The order status and inventory flag make the operation idempotent. All stock
    restorations, order transitions, and audit records are committed together.
    """
    if isinstance(older_than_hours, bool) or not isinstance(older_than_hours, int):
        raise ValueError("older_than_hours must be a positive whole number.")
    if older_than_hours < 1 or older_than_hours > 720:
        raise ValueError("older_than_hours must be between 1 and 720.")

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=older_than_hours)
    session = db.session
    eligible = session.execute(
        select(Order)
        .where(
            Order.payment_status == "awaiting_verification",
            Order.inventory_deducted.is_(True),
            Order.created_at <= cutoff,
        )
        .order_by(Order.id.asc())
        .with_for_update()
    ).scalars().all()

    if dry_run:
        return {"examined": len(eligible), "expired": 0, "dry_run": True, "order_ids": [o.id for o in eligible]}

    expired_ids = []
    try:
        for order in eligible:
            items = session.execute(
                select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.product_id.asc())
            ).scalars().all()
            for item in items:
                result = session.execute(
                    update(Product)
                    .where(Product.id == item.product_id)
                    .values(stock=Product.stock + item.quantity)
                )
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"Cannot restore inventory for order {order.id}: product {item.product_id} is missing."
                    )

            order.payment_status = "expired"
            order.fulfillment_status = "payment_issue"
            order.inventory_deducted = False
            session.add(
                PaymentAuditLog(
                    order_id=order.id,
                    event="payment_expired",
                    details=f"Payment verification expired after {older_than_hours} hours; reserved inventory was released.",
                    actor="system",
                )
            )
            expired_ids.append(order.id)

        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "examined": len(eligible),
        "expired": len(expired_ids),
        "dry_run": False,
        "order_ids": expired_ids,
    }
