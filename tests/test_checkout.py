import io
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from PIL import Image
from pypdf import PdfWriter
from sqlalchemy.exc import IntegrityError

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import (
    CheckoutError,
    create_app,
    parse_product_form,
    seed_products,
    validate_receipt_upload,
)
from app.models import Order, OrderItem, PaymentAuditLog, Product, db
from werkzeug.datastructures import FileStorage


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


class CheckoutHardeningTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            seed_products()
        self.storage = MemoryReceiptStorage()
        self.app.extensions["receipt_storage"] = self.storage
        self.client = self.app.test_client()
        self.client.get("/checkout")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def csrf_token(self):
        with self.client.session_transaction() as session:
            return session["customer_csrf_token"]

    def checkout_data(self, **overrides):
        data = {
            "csrf_token": self.csrf_token(),
            "name": "Guest Buyer",
            "email": "guest@example.test",
            "payment_method": "manual_transfer",
            "reference": "TEST-REFERENCE",
            "receipt": (valid_png(), "receipt.png"),
        }
        data.update(overrides)
        return data

    def delivery_data(self, **overrides):
        data = {
            "csrf_token": self.csrf_token(),
            "stage": "delivery",
            "delivery_recipient_name": "Guest Buyer",
            "delivery_phone": "+2348012345678",
            "delivery_email": "guest@example.test",
            "delivery_state": "Oyo",
            "delivery_city": "Ibadan",
            "delivery_address": "12 Example Street",
            "delivery_landmark": "Near the market",
        }
        data.update(overrides)
        return data

    def submit_complete_checkout(self, **payment_overrides):
        payment = self.client.post("/checkout", data=self.checkout_data(**payment_overrides))
        self.assertEqual(payment.status_code, 302)
        self.assertIn("stage=delivery", payment.location)
        return self.client.post("/checkout", data=self.delivery_data())

    def test_checkout_uses_database_prices_and_reserves_stock_atomically(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2, "price": "0.01"}]

        response = self.client.post(
            "/checkout",
            data=self.checkout_data(
                cart='[{"product_id": 2, "quantity": 1}]',
                receipt_file="/static/uploads/payments/forged.png",
            ),
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.post("/checkout", data=self.delivery_data())
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            product = db.session.get(Product, 1)
            order = Order.query.one()
            item = OrderItem.query.filter_by(order_id=order.id).one()
            self.assertEqual(product.stock, 23)
            self.assertEqual(order.total_amount, Decimal("60.00"))
            self.assertEqual(item.unit_price, Decimal("30.00"))
            self.assertTrue(order.inventory_deducted)
            self.assertRegex(order.receipt_file, r"^receipts/[a-f0-9]{32}\.png$")
            self.assertEqual(PaymentAuditLog.query.filter_by(order_id=order.id).count(), 1)

        public_receipt = self.client.get(
            "/static/uploads/payments/20261112153325_receipt.png"
        )
        self.assertEqual(public_receipt.status_code, 404)
        with self.client.session_transaction() as session:
            self.assertEqual(session["cart"], [])

    def test_payment_stage_does_not_create_order_or_deduct_stock(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2}]
        response = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 25)
        self.assertEqual(len(self.storage.files), 1)

    def test_invalid_delivery_keeps_receipt_and_cart_for_retry(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        self.client.post("/checkout", data=self.checkout_data())
        response = self.client.post("/checkout", data=self.delivery_data(delivery_address=""))
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 25)
        with self.client.session_transaction() as session:
            self.assertIn("checkout_draft", session)
            self.assertEqual(len(session["cart"]), 1)
        self.assertEqual(len(self.storage.files), 1)

    def test_shop_to_cart_flow_uses_csrf_and_live_catalog(self):
        response = self.client.get("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Niacinamide Balancing Serum", response.data)

        response = self.client.post(
            "/cart/add",
            data={
                "csrf_token": self.csrf_token(),
                "product_id": "1",
                "quantity": "2",
            },
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/cart")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Niacinamide Balancing Serum", response.data)
        self.assertIn("₦60.00".encode(), response.data)

    def test_checkout_rejects_forged_receipt_paths_and_invalid_files(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post(
            "/checkout",
            data=self.checkout_data(receipt=(io.BytesIO(b"not an image"), "receipt.png")),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"invalid or unreadable", response.data)

        with self.assertRaises(CheckoutError):
            validate_receipt_upload(
                FileStorage(stream=valid_png(), filename="..\\receipt.png"),
                5 * 1024 * 1024,
            )

        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post(
            "/checkout",
            data=self.checkout_data(receipt=(None, "")),
        )
        self.assertEqual(response.status_code, 400)

        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 25)

    def test_checkout_stock_conflict_does_not_create_order_or_consume_receipt(self):
        with self.app.app_context():
            db.session.get(Product, 1).stock = 1
            db.session.commit()
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2}]

        payment = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(payment.status_code, 302)
        response = self.client.post("/checkout", data=self.delivery_data())
        self.assertEqual(response.status_code, 409)
        self.assertIn(b"Only 1 unit", response.data)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 1)
        self.assertEqual(len(self.storage.files), 1)
        with self.client.session_transaction() as session:
            self.assertIn("checkout_draft", session)
            self.assertEqual(len(session["cart"]), 1)

    def test_checkout_requires_configured_private_storage(self):
        self.app.extensions["receipt_storage"] = None
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]

        response = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Private receipt storage is not configured", response.data)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 25)

    def test_receipt_validation_accepts_pdf_and_rejects_mismatch_and_oversize(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        pdf = io.BytesIO()
        writer.write(pdf)
        pdf.seek(0)
        data, extension, content_type = validate_receipt_upload(
            FileStorage(stream=pdf, filename="payment.pdf"), 5 * 1024 * 1024
        )
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(extension, "pdf")
        self.assertEqual(content_type, "application/pdf")

        with self.assertRaisesRegex(CheckoutError, "does not match"):
            validate_receipt_upload(
                FileStorage(stream=valid_png(), filename="payment.jpg"),
                5 * 1024 * 1024,
            )
        with self.assertRaisesRegex(CheckoutError, "5 MB or smaller"):
            validate_receipt_upload(
                FileStorage(stream=io.BytesIO(b"x" * 11), filename="payment.pdf"),
                10,
            )

    def test_receipt_download_requires_admin_and_is_an_attachment(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.submit_complete_checkout()
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            order_id = Order.query.one().id
            receipt_key = Order.query.one().receipt_file

        response = self.client.get(f"/admin/orders/{order_id}/receipt")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)

        self.client.get("/admin/login")
        with self.client.session_transaction() as session:
            admin_token = session["admin_csrf_token"]
        login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": admin_token,
                "username": "test-admin",
                "password": "test-admin-password",
            },
        )
        self.assertEqual(login.status_code, 302)

        response = self.client.get(f"/admin/orders/{order_id}/receipt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Disposition"], f'attachment; filename=order-{order_id}-receipt.png')
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.data, self.storage.files[receipt_key][0])

    def test_checkout_database_failure_rolls_back_reserved_stock(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 2}]
        payment = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(payment.status_code, 302)
        with patch(
            "app.app.db.session.flush",
            side_effect=IntegrityError("simulated failure", {}, Exception()),
        ):
            response = self.client.post("/checkout", data=self.delivery_data())

        self.assertEqual(response.status_code, 500)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 0)
            self.assertEqual(db.session.get(Product, 1).stock, 25)
        self.assertEqual(len(self.storage.files), 1)
        with self.client.session_transaction() as session:
            self.assertIn("checkout_draft", session)

    def test_requests_do_not_create_schema_and_seed_command_is_idempotent(self):
        with self.app.app_context():
            db.drop_all()
            self.assertEqual(db.inspect(db.engine).get_table_names(), [])

        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            self.assertEqual(db.inspect(db.engine).get_table_names(), [])
            db.create_all()

        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["seed-products"])
        second = runner.invoke(args=["seed-products"])
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("Seeded 4 product(s).", first.output)
        self.assertIn("Seeded 0 product(s).", second.output)

    def test_product_prices_require_exact_cents_and_bounded_precision(self):
        values = {
            "name": "Test Product",
            "skin_type": "all",
            "price": "12.34",
            "stock": "3",
        }
        parsed, error = parse_product_form(values)
        self.assertIsNone(error)
        self.assertEqual(parsed["price"], Decimal("12.34"))

        for price in ("12.345", "1e100"):
            parsed, error = parse_product_form({**values, "price": price})
            self.assertIsNone(parsed)
            self.assertIsNotNone(error)


    def test_guest_checkout_creates_order_without_customer_account_and_snapshots_delivery(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]

        response = self.submit_complete_checkout()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/payment?ref=TEST-REFERENCE", response.location)

        with self.app.app_context():
            order = Order.query.one()
            self.assertIsNone(order.customer_id)
            self.assertEqual(order.delivery_recipient_name, "Guest Buyer")
            self.assertEqual(order.delivery_phone, "+2348012345678")
            self.assertEqual(order.delivery_email, "guest@example.test")
            self.assertEqual(order.delivery_state, "Oyo")
            self.assertEqual(order.delivery_city, "Ibadan")
            self.assertEqual(order.delivery_address, "12 Example Street")
            self.assertEqual(order.delivery_landmark, "Near the market")

    def test_duplicate_payment_reference_is_rejected_before_receipt_storage(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.submit_complete_checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.storage.files), 1)

        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(response.status_code, 409)
        self.assertIn(b"already been used", response.data)
        self.assertEqual(len(self.storage.files), 1)
        with self.app.app_context():
            self.assertEqual(Order.query.count(), 1)

    def test_payment_stage_rejects_invalid_email_address(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post(
            "/checkout", data=self.checkout_data(email="not-an-email")
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid customer email", response.data)
        self.assertEqual(len(self.storage.files), 0)

    def test_delivery_stage_rejects_invalid_email_and_preserves_draft(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        self.client.post("/checkout", data=self.checkout_data())
        response = self.client.post(
            "/checkout",
            data=self.delivery_data(delivery_email="not-an-email"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid delivery email", response.data)
        with self.client.session_transaction() as session:
            self.assertIn("checkout_draft", session)
            self.assertEqual(len(session["cart"]), 1)
        self.assertEqual(len(self.storage.files), 1)


    def test_signed_in_customer_address_is_saved_and_order_snapshot_is_immutable(self):
        from app.models import Customer

        with self.app.app_context():
            customer = Customer(
                full_name="Account Buyer",
                email="account@example.test",
                phone_number="+2348000000000",
                password_hash="test-hash",
            )
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        with self.client.session_transaction() as session:
            session["customer_id"] = customer_id
            session["customer_name"] = "Account Buyer"
            session["cart"] = [{"product_id": 1, "quantity": 1}]

        payment = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(payment.status_code, 302)
        delivery = self.client.post(
            "/checkout",
            data=self.delivery_data(
                delivery_recipient_name="Recipient One",
                delivery_address="12 First Street",
                delivery_landmark="Blue gate",
            ),
        )
        self.assertEqual(delivery.status_code, 302)

        with self.app.app_context():
            customer = db.session.get(Customer, customer_id)
            order = Order.query.one()
            self.assertEqual(customer.delivery_state, "Oyo")
            self.assertEqual(customer.delivery_city, "Ibadan")
            self.assertEqual(customer.delivery_address, "12 First Street")
            self.assertEqual(customer.delivery_landmark, "Blue gate")
            self.assertEqual(customer.phone_number, "+2348012345678")
            customer.delivery_state = "Lagos"
            customer.delivery_city = "Ikeja"
            customer.delivery_address = "99 New Street"
            customer.delivery_landmark = "Red gate"
            db.session.commit()
            db.session.refresh(order)
            self.assertEqual(order.delivery_state, "Oyo")
            self.assertEqual(order.delivery_city, "Ibadan")
            self.assertEqual(order.delivery_address, "12 First Street")
            self.assertEqual(order.delivery_landmark, "Blue gate")

    def test_expired_checkout_draft_deletes_receipt_and_returns_to_payment_stage(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        payment = self.client.post("/checkout", data=self.checkout_data())
        self.assertEqual(payment.status_code, 302)
        with self.client.session_transaction() as session:
            receipt_key = session["checkout_draft"]["receipt_key"]
            session["checkout_draft"]["expires_at"] = 1

        response = self.client.get("/checkout?stage=delivery")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Payment verification", response.data)
        self.assertNotIn(receipt_key, self.storage.files)
        with self.client.session_transaction() as session:
            self.assertNotIn("checkout_draft", session)

    def test_checkout_validation_errors_render_page_and_preserve_delivery_values(self):
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        self.client.post("/checkout", data=self.checkout_data())
        response = self.client.post(
            "/checkout",
            data=self.delivery_data(
                delivery_email="invalid-email",
                delivery_city="Abeokuta",
                delivery_address="42 Retained Road",
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'class="checkout-error" role="alert"', response.data)
        self.assertIn(b"valid delivery email", response.data)
        self.assertIn(b'value="Abeokuta"', response.data)
        self.assertIn(b"42 Retained Road", response.data)
        self.assertEqual(len(self.storage.files), 1)


if __name__ == "__main__":
    unittest.main()
