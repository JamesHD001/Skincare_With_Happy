import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app, seed_products
from app.models import Order, OrderItem, PaymentAuditLog, Product, db
from app.order_maintenance import expire_unverified_orders


class StaleOrderMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            seed_products()
            product = db.session.get(Product, 1)
            product.stock = 8
            order = Order(
                customer_name="Test Buyer",
                user_email="buyer@example.test",
                total_amount=Decimal("60.00"),
                inventory_deducted=True,
                payment_method="manual_transfer",
                payment_status="awaiting_verification",
                fulfillment_status="pending",
                payment_reference="STALE-ORDER-1",
                created_at=datetime.utcnow() - timedelta(hours=72),
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=2,
                unit_price=Decimal("30.00"),
            ))
            self.stale_order_id = order.id

            paid = Order(
                customer_name="Paid Buyer",
                user_email="paid@example.test",
                total_amount=Decimal("30.00"),
                inventory_deducted=True,
                payment_method="manual_transfer",
                payment_status="paid",
                fulfillment_status="processing",
                payment_reference="PAID-ORDER-1",
                created_at=datetime.utcnow() - timedelta(hours=96),
            )
            db.session.add(paid)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=paid.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal("30.00"),
            ))
            self.paid_order_id = paid.id
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_dry_run_reports_candidates_without_mutating_orders_or_stock(self):
        with self.app.app_context():
            result = expire_unverified_orders(db, older_than_hours=48, dry_run=True)
            self.assertEqual(result["order_ids"], [self.stale_order_id])
            self.assertEqual(result["expired"], 0)
            self.assertEqual(db.session.get(Product, 1).stock, 8)
            order = db.session.get(Order, self.stale_order_id)
            self.assertEqual(order.payment_status, "awaiting_verification")
            self.assertTrue(order.inventory_deducted)
            self.assertEqual(PaymentAuditLog.query.count(), 0)

    def test_expiry_restores_stock_and_records_audit_atomically(self):
        with self.app.app_context():
            result = expire_unverified_orders(db, older_than_hours=48)
            self.assertEqual(result["expired"], 1)
            self.assertEqual(db.session.get(Product, 1).stock, 10)
            order = db.session.get(Order, self.stale_order_id)
            self.assertEqual(order.payment_status, "expired")
            self.assertEqual(order.fulfillment_status, "payment_issue")
            self.assertFalse(order.inventory_deducted)
            audit = PaymentAuditLog.query.filter_by(order_id=self.stale_order_id).one()
            self.assertEqual(audit.event, "payment_expired")
            self.assertEqual(audit.actor, "system")

    def test_expiry_is_idempotent_and_does_not_touch_paid_orders(self):
        with self.app.app_context():
            first = expire_unverified_orders(db, older_than_hours=48)
            second = expire_unverified_orders(db, older_than_hours=48)
            self.assertEqual(first["expired"], 1)
            self.assertEqual(second["expired"], 0)
            self.assertEqual(db.session.get(Product, 1).stock, 10)
            paid = db.session.get(Order, self.paid_order_id)
            self.assertEqual(paid.payment_status, "paid")
            self.assertTrue(paid.inventory_deducted)
            self.assertEqual(PaymentAuditLog.query.filter_by(event="payment_expired").count(), 1)

    def test_expiry_rejects_unsafe_timeout_values(self):
        with self.app.app_context():
            for hours in (0, -1, 721, True, 1.5):
                with self.subTest(hours=hours):
                    with self.assertRaises(ValueError):
                        expire_unverified_orders(db, older_than_hours=hours)

    def test_cli_supports_dry_run_and_explicit_timeout(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["expire-unverified-orders", "--dry-run", "--older-than-hours", "48"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Examined 1 eligible order(s); expired 0", result.output)
        with self.app.app_context():
            self.assertEqual(db.session.get(Product, 1).stock, 8)


if __name__ == "__main__":
    unittest.main()
