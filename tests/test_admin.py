import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app, seed_products
from app.models import AdminProfile, Order, OrderItem, PaymentAuditLog, Product, db
from werkzeug.security import check_password_hash


class AdminConsoleTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            seed_products()
        self.client = self.app.test_client()
        self.client.get("/admin/login")

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def csrf_token(self):
        with self.client.session_transaction() as session:
            return session["admin_csrf_token"]

    def sign_in(self):
        return self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf_token(),
                "username": "test-admin",
                "password": "test-admin-password",
            },
        )

    def test_admin_routes_require_login_and_csrf(self):
        for path in ("/admin", "/admin/orders", "/admin/products", "/admin/customers", "/admin/settings"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/admin/login", response.location)

        response = self.client.post("/admin/login", data={"username": "test-admin", "password": "test-admin-password"})
        self.assertEqual(response.status_code, 400)

        response = self.sign_in()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        with self.client.session_transaction() as session:
            session["cart"] = [{"product_id": 1, "quantity": 1}]
        response = self.client.post(
            "/admin/logout",
            data={"csrf_token": self.csrf_token()},
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertIn("cart", session)
            self.assertNotIn("admin_authenticated", session)

    def test_dashboard_and_product_catalog_use_live_data(self):
        self.sign_in()
        response = self.client.post(
            "/admin/products",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Calming Oat Moisturizer",
                "skin_type": "sensitive",
                "price": "14500",
                "stock": "3",
                "description": "A gentle barrier-supporting cream.",
            },
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            product = Product.query.filter_by(name="Calming Oat Moisturizer").one()
            product_id = product.id

        response = self.client.get("/admin")
        self.assertIn(b"1 at or below 5 units", response.data)
        self.assertIn("₦14,500.00".encode(), response.data)

        response = self.client.post(
            f"/admin/products/{product_id}/edit",
            data={
                "csrf_token": self.csrf_token(),
                "name": "Calming Oat Moisturizer",
                "skin_type": "sensitive",
                "price": "15000",
                "stock": "12",
                "description": "Updated description.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/admin/products").status_code, 200)
        with self.app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.stock, 12)
            self.assertEqual(product.price, 15000)

    def test_admin_login_stays_disabled_without_credentials(self):
        with patch("app.app.ADMIN_USERNAME", ""), patch("app.app.ADMIN_PASSWORD", ""):
            response = self.client.get("/admin/login")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Admin access is disabled", response.data)
            response = self.client.post(
                "/admin/login",
                data={
                    "csrf_token": self.csrf_token(),
                    "username": "test-admin",
                    "password": "test-admin-password",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Admin login is not configured", response.data)
            self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_profile_settings_and_password_change_persist(self):
        self.sign_in()
        response = self.client.post(
            "/admin/settings",
            data={
                "csrf_token": self.csrf_token(),
                "display_name": "Amina Happy",
                "email": "amina@example.test",
                "phone": "+2348000000000",
                "bio": "Helping customers build calm, healthy skin routines.",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            profile = AdminProfile.query.one()
            self.assertEqual(profile.display_name, "Amina Happy")
            self.assertEqual(profile.email, "amina@example.test")
            self.assertEqual(profile.phone, "+2348000000000")
            self.assertEqual(profile.bio, "Helping customers build calm, healthy skin routines.")

        response = self.client.post(
            "/admin/settings/password",
            data={
                "csrf_token": self.csrf_token(),
                "current_password": "test-admin-password",
                "new_password": "new-admin-password-2026",
                "confirm_password": "new-admin-password-2026",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            profile = AdminProfile.query.one()
            self.assertTrue(check_password_hash(profile.password_hash, "new-admin-password-2026"))
            self.assertNotEqual(profile.password_hash, "new-admin-password-2026")

        self.client.post("/admin/logout", data={"csrf_token": self.csrf_token()})
        token = self.csrf_token()
        old_password_response = self.client.post(
            "/admin/login",
            data={"csrf_token": token, "username": "test-admin", "password": "test-admin-password"},
        )
        self.assertEqual(old_password_response.status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 302)

        with patch("app.app.ADMIN_PASSWORD", ""):
            new_password_response = self.client.post(
                "/admin/login",
                data={
                    "csrf_token": self.csrf_token(),
                    "username": "test-admin",
                    "password": "new-admin-password-2026",
                },
            )
            self.assertEqual(new_password_response.status_code, 302)
            self.assertEqual(self.client.get("/admin/settings").status_code, 200)

    def test_payment_review_records_admin_and_customer_summary(self):
        self.sign_in()
        with self.app.app_context():
            product = Product.query.first()
            starting_stock = product.stock
            product_id = product.id
            product.stock -= 2
            order = Order(
                customer_name="Amina Buyer",
                user_email="amina@example.test",
                phone_number="08000000000",
                total_amount=12500,
                inventory_deducted=True,
                payment_method="manual_transfer",
                payment_status="awaiting_verification",
                fulfillment_status="pending",
                payment_reference="TEST-ORDER-1",
                receipt_file="receipts/0123456789abcdef0123456789abcdef.png",
            )
            order.items.append(OrderItem(product_id=product.id, quantity=2, unit_price=product.price))
            db.session.add(order)
            db.session.commit()
            order_id = order.id

        response = self.client.post(
            f"/admin/orders/{order_id}/verify",
            data={"csrf_token": self.csrf_token(), "decision": "approve"},
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.get("/admin")
        self.assertIn("₦12,500.00".encode(), response.data)

        with self.app.app_context():
            order = db.session.get(Order, order_id)
            self.assertEqual(order.payment_status, "paid")
            self.assertTrue(order.inventory_deducted)
            audit = PaymentAuditLog.query.filter_by(order_id=order_id).one()
            self.assertEqual(audit.event, "payment_approved")
            self.assertEqual(audit.actor, "test-admin")

        response = self.client.get("/admin/orders")
        self.assertIn(b"Download receipt", response.data)

        with self.app.app_context():
            product = Product.query.first()
            product.stock -= 1
            rejected_order = Order(
                customer_name="Rejected Buyer",
                user_email="rejected@example.test",
                total_amount=product.price,
                inventory_deducted=True,
                payment_method="manual_transfer",
                payment_status="awaiting_verification",
                fulfillment_status="pending",
                payment_reference="TEST-ORDER-2",
            )
            rejected_order.items.append(
                OrderItem(product_id=product.id, quantity=1, unit_price=product.price)
            )
            db.session.add(rejected_order)
            db.session.commit()
            rejected_order_id = rejected_order.id

        response = self.client.post(
            f"/admin/orders/{rejected_order_id}/verify",
            data={"csrf_token": self.csrf_token(), "decision": "reject"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            order = db.session.get(Order, rejected_order_id)
            self.assertEqual(order.payment_status, "rejected")
            self.assertFalse(order.inventory_deducted)
            self.assertEqual(db.session.get(Product, product_id).stock, starting_stock - 2)

        response = self.client.get("/admin/customers")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"amina@example.test", response.data)
        with self.app.app_context():
            self.assertEqual(PaymentAuditLog.query.filter_by(order_id=order_id).count(), 1)


if __name__ == "__main__":
    unittest.main()
