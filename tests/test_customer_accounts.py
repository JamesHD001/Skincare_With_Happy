import io
import os
import unittest

from PIL import Image

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app, seed_products
from app.models import Customer, Order, db
from werkzeug.security import check_password_hash


class MemoryReceiptStorage:
    def __init__(self):
        self.files = {}

    def save(self, data, extension, content_type):
        key = f"receipts/{len(self.files):032x}.{extension}"
        self.files[key] = (data, content_type)
        return key

    def read(self, key, max_bytes):
        return self.files[key][0]

    def delete(self, key):
        self.files.pop(key, None)


def valid_png():
    image = Image.new("RGB", (1, 1), color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


class CustomerAccountTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            seed_products()
        self.app.extensions["receipt_storage"] = MemoryReceiptStorage()
        self.client = self.app.test_client()
        self.client.get("/signup")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def csrf_token(self):
        with self.client.session_transaction() as session:
            return session["customer_csrf_token"]

    def sign_up(self, email="happy@example.test"):
        return self.client.post(
            "/signup",
            data={
                "csrf_token": self.csrf_token(),
                "full_name": "Amina Happy",
                "email": email,
                "phone_number": "+2348000000000",
                "password": "secure-customer-password",
            },
        )

    def test_signup_normalizes_email_hashes_password_and_checks_csrf(self):
        response = self.client.post(
            "/signup",
            data={
                "full_name": "Amina Happy",
                "email": "happy@example.test",
                "password": "secure-customer-password",
            },
        )
        self.assertEqual(response.status_code, 400)

        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2}]
        oversized_email = self.client.post(
            "/signup",
            data={
                "csrf_token": self.csrf_token(),
                "full_name": "Amina Happy",
                "email": f"{'a' * 250}@example.test",
                "password": "secure-customer-password",
            },
        )
        self.assertEqual(oversized_email.status_code, 200)
        self.assertIn(b"254 characters or fewer", oversized_email.data)

        response = self.sign_up("  Happy@Example.Test  ")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/account")
        self.assertEqual(self.client.get("/account").status_code, 200)

        with self.app.app_context():
            customer = Customer.query.one()
            self.assertEqual(customer.email, "happy@example.test")
            self.assertTrue(check_password_hash(customer.password_hash, "secure-customer-password"))
            self.assertNotEqual(customer.password_hash, "secure-customer-password")

        with self.client.session_transaction() as session:
            self.assertIn("cart", session)
            self.assertEqual(session["cart"][0]["quantity"], 2)

        self.client.post("/signout", data={"csrf_token": self.csrf_token()})
        duplicate = self.sign_up("HAPPY@example.test")
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn(b"already exists", duplicate.data)
        with self.app.app_context():
            self.assertEqual(Customer.query.count(), 1)

    def test_signin_signout_and_protected_account_preserve_cart(self):
        self.sign_up()
        self.client.post("/signout", data={"csrf_token": self.csrf_token()})

        response = self.client.get("/account")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/signin", response.location)

        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        bad_password = self.client.post(
            "/signin",
            data={
                "csrf_token": self.csrf_token(),
                "email": "happy@example.test",
                "password": "incorrect-password",
            },
        )
        self.assertEqual(bad_password.status_code, 200)
        self.assertIn(b"Email or password is incorrect", bad_password.data)

        response = self.client.post(
            "/signin",
            data={
                "csrf_token": self.csrf_token(),
                "email": "HAPPY@example.test",
                "password": "secure-customer-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/account")
        self.assertEqual(self.client.get("/account").status_code, 200)

        response = self.client.post("/signout", data={"csrf_token": self.csrf_token()})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertIn("cart", session)
            self.assertNotIn("customer_id", session)

    def test_authenticated_checkout_links_order_and_history_ignores_guest_orders(self):
        self.sign_up()
        with self.app.app_context():
            customer = Customer.query.one()
            guest_order = Order(
                customer_name="Amina Happy",
                user_email=customer.email,
                total_amount=100,
                payment_method="manual_transfer",
                payment_status="awaiting_verification",
                fulfillment_status="pending",
                payment_reference="GUEST-HISTORY-ORDER",
            )
            db.session.add(guest_order)
            db.session.commit()
            guest_order_id = guest_order.id

        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2}]
        response = self.client.post(
            "/checkout",
            data={
                "csrf_token": self.csrf_token(),
                "payment_method": "manual_transfer",
                "reference": "SIGNED-CUSTOMER-ORDER",
                "phone": "+2348000000000",
                "receipt": (valid_png(), "receipt.png"),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/payment?ref=SIGNED-CUSTOMER-ORDER", response.location)

        with self.app.app_context():
            customer = Customer.query.one()
            signed_order = Order.query.filter_by(payment_reference="SIGNED-CUSTOMER-ORDER").one()
            self.assertEqual(signed_order.customer_id, customer.id)
            self.assertEqual(signed_order.user_email, customer.email)
            self.assertEqual(signed_order.customer_name, customer.full_name)
            self.assertIsNone(db.session.get(Order, guest_order_id).customer_id)

        history = self.client.get("/account")
        self.assertIn(f"Order #{signed_order.id}".encode(), history.data)
        self.assertNotIn(f"Order #{guest_order_id}".encode(), history.data)

    def test_guest_checkout_stays_available_and_unlinked(self):
        self.client.get("/checkout")
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post(
            "/checkout",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Guest Buyer",
                "email": "Guest@Example.Test",
                "payment_method": "manual_transfer",
                "reference": "GUEST-CHECKOUT-ORDER",
                "receipt": (valid_png(), "receipt.png"),
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            order = Order.query.filter_by(payment_reference="GUEST-CHECKOUT-ORDER").one()
            self.assertIsNone(order.customer_id)
            self.assertEqual(order.user_email, "guest@example.test")
            self.assertEqual(order.customer_name, "Guest Buyer")


if __name__ == "__main__":
    unittest.main()
