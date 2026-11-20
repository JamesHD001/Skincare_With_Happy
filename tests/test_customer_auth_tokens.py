import os
import unittest
from datetime import datetime, timedelta

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app
from app.customer_auth_tokens import (
    consume_customer_token,
    invalidate_customer_tokens,
    issue_customer_token,
)
from app.models import Customer, CustomerAuthToken, db
from werkzeug.security import generate_password_hash


class CustomerAuthTokenTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            self.customer = Customer(
                full_name="Token Test",
                email="token@example.test",
                password_hash=generate_password_hash("a-secure-test-password"),
            )
            db.session.add(self.customer)
            db.session.commit()
            self.customer_id = self.customer.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def test_raw_token_is_not_stored_and_valid_token_is_single_use(self):
        with self.app.app_context():
            customer = db.session.get(Customer, self.customer_id)
            raw_token = issue_customer_token(db, customer, purpose="email_verification")
            record = CustomerAuthToken.query.one()
            self.assertNotEqual(record.token_hash, raw_token)
            self.assertEqual(len(record.token_hash), 64)

            consumed = consume_customer_token(
                db, raw_token, purpose="email_verification"
            )
            self.assertEqual(consumed.id, self.customer_id)
            self.assertIsNotNone(record.used_at)
            self.assertIsNone(
                consume_customer_token(db, raw_token, purpose="email_verification")
            )

    def test_expired_and_wrong_purpose_tokens_are_rejected(self):
        with self.app.app_context():
            customer = db.session.get(Customer, self.customer_id)
            expired_token = issue_customer_token(
                db,
                customer,
                purpose="password_reset",
                lifetime_minutes=1,
                now=datetime(2026, 1, 1, 12, 0, 0),
            )
            self.assertIsNone(
                consume_customer_token(
                    db,
                    expired_token,
                    purpose="password_reset",
                    now=datetime(2026, 1, 1, 12, 1, 0),
                )
            )
            self.assertIsNone(
                consume_customer_token(
                    db,
                    expired_token,
                    purpose="email_verification",
                    now=datetime(2026, 1, 1, 12, 0, 30),
                )
            )

    def test_invalidation_revokes_all_outstanding_tokens_for_purpose(self):
        with self.app.app_context():
            customer = db.session.get(Customer, self.customer_id)
            first = issue_customer_token(db, customer, purpose="password_reset")
            second = issue_customer_token(db, customer, purpose="password_reset")
            verification = issue_customer_token(db, customer, purpose="email_verification")
            self.assertEqual(
                invalidate_customer_tokens(db, customer, purpose="password_reset"), 2
            )
            self.assertIsNone(
                consume_customer_token(db, first, purpose="password_reset")
            )
            self.assertIsNone(
                consume_customer_token(db, second, purpose="password_reset")
            )
            self.assertIsNotNone(
                consume_customer_token(db, verification, purpose="email_verification")
            )

    def test_invalid_purpose_and_lifetime_are_rejected(self):
        with self.app.app_context():
            customer = db.session.get(Customer, self.customer_id)
            with self.assertRaises(ValueError):
                issue_customer_token(db, customer, purpose="other")
            with self.assertRaises(ValueError):
                issue_customer_token(db, customer, purpose="password_reset", lifetime_minutes=0)
            with self.assertRaises(ValueError):
                issue_customer_token(db, customer, purpose="password_reset", lifetime_minutes=True)


if __name__ == "__main__":
    unittest.main()
