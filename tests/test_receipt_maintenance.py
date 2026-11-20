import os
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app
from app.models import Order, db
from app.receipt_maintenance import cleanup_orphaned_receipts


class FakeReceiptStorage:
    def __init__(self, objects):
        self.objects = objects
        self.deleted = []

    def list_receipts(self, *, older_than):
        return [
            (key, modified)
            for key, modified in self.objects
            if modified <= older_than
        ]

    def delete(self, key):
        self.deleted.append(key)


class OrphanedReceiptCleanupTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            db.session.add(Order(
                customer_name="Receipt Owner",
                user_email="owner@example.test",
                total_amount=Decimal("20.00"),
                payment_reference="ORDER-RECEIPT-1",
                receipt_file="receipts/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
            ))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def storage(self):
        old = datetime.now(timezone.utc) - timedelta(days=10)
        recent = datetime.now(timezone.utc) - timedelta(days=2)
        return FakeReceiptStorage([
            ("receipts/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png", old),
            ("receipts/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png", old),
            ("receipts/cccccccccccccccccccccccccccccccc.png", recent),
        ])

    def test_dry_run_only_identifies_old_unreferenced_receipts(self):
        with self.app.app_context():
            storage = self.storage()
            result = cleanup_orphaned_receipts(db, storage, older_than_days=7, dry_run=True)
            self.assertEqual(result["examined"], 1)
            self.assertEqual(result["deleted"], 0)
            self.assertEqual(result["keys"], ["receipts/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"])
            self.assertEqual(storage.deleted, [])

    def test_cleanup_deletes_only_old_orphans_and_preserves_order_receipts(self):
        with self.app.app_context():
            storage = self.storage()
            result = cleanup_orphaned_receipts(db, storage, older_than_days=7)
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(storage.deleted, ["receipts/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"])
            self.assertNotIn("receipts/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png", storage.deleted)

    def test_cleanup_rejects_invalid_age_and_unsupported_storage(self):
        with self.app.app_context():
            for days in (0, -1, 366, True, 1.5):
                with self.subTest(days=days):
                    with self.assertRaises(ValueError):
                        cleanup_orphaned_receipts(db, self.storage(), older_than_days=days)
            with self.assertRaises(RuntimeError):
                cleanup_orphaned_receipts(db, object(), older_than_days=7)


if __name__ == "__main__":
    unittest.main()
