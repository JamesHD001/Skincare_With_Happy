import io
import os
import re
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ADMIN_USERNAME"] = "test-admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-session-secret"

from app.app import create_app, seed_products
from app.models import Product, db
from app.product_image_storage import (
    MAX_IMAGE_DIMENSION,
    ProductImageError,
    ProductImageStorageError,
    create_product_image_storage,
    validate_product_image,
)


def image_file(image_format="PNG", size=(40, 60)):
    output = io.BytesIO()
    Image.new("RGB", size, color=(210, 170, 140)).save(output, format=image_format)
    output.seek(0)
    return output


class MemoryProductImageStorage:
    def __init__(self):
        self.files = {}
        self.fail_save = False
        self.fail_delete = False

    def save(self, data):
        if self.fail_save:
            raise ProductImageStorageError("Product image storage is unavailable.")
        key = f"products/{len(self.files):032x}.webp"
        self.files[key] = data
        return key

    def delete(self, key):
        if self.fail_delete:
            raise ProductImageStorageError("Product image cleanup failed.")
        self.files.pop(key, None)

    def public_url(self, key):
        if not re.fullmatch(r"products/[a-f0-9]{32}\.webp", key or ""):
            return None
        return f"https://images.example.test/{key}"


class ProductCatalogTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        with self.app.app_context():
            db.create_all()
            seed_products()
        self.assertIsNone(self.app.extensions["product_image_storage"])
        self.storage = MemoryProductImageStorage()
        self.app.extensions["product_image_storage"] = self.storage
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

    def product_form(self, **overrides):
        data = {
            "csrf_token": self.csrf_token(),
            "name": "Calming Daily Lotion",
            "skin_type": "sensitive",
            "price": "22.50",
            "stock": "6",
            "description": "A calm and simple daily routine.",
        }
        data.update(overrides)
        return data

    def test_storefront_lists_database_products_with_shared_cards_and_images(self):
        for path in ("/", "/shop", "/products"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data.count(b'class="catalog-card"'), 4)
                self.assertIn(b"niacinamide-balancing-serum.svg", response.data)
                self.assertIn(b"Add to cart", response.data)
                self.assertIn(b"Newsletter subscriptions are not available yet.", response.data)

        filtered = self.client.get("/products?type=oily")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data.count(b'class="catalog-card"'), 1)
        self.assertIn(b"Niacinamide Balancing Serum", filtered.data)
        self.assertNotIn(b"Gentle Cream Cleanser", filtered.data)

        shop_filtered = self.client.get("/shop?type=oily")
        self.assertEqual(shop_filtered.status_code, 200)
        self.assertEqual(shop_filtered.data.count(b'class="catalog-card"'), 1)
        self.assertIn(b"Niacinamide Balancing Serum", shop_filtered.data)
        self.assertIn(b"<h2>Oily skin</h2>", shop_filtered.data)
        self.assertEqual(shop_filtered.data.count(b">All skin types</option>"), 1)

        detail = self.client.get("/product/1")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"Niacinamide Balancing Serum", detail.data)
        self.assertIn(b"niacinamide-balancing-serum.svg", detail.data)

        with self.client.session_transaction() as session:
            self.assertTrue(session.get("customer_csrf_token"))

    def test_missing_image_uses_brand_fallback(self):
        with self.app.app_context():
            product = Product(
                name="Image Pending Product",
                slug="image-pending-product",
                skin_type="all",
                price="12.00",
                stock=0,
            )
            db.session.add(product)
            db.session.commit()
            product_id = product.id

        response = self.client.get(f"/product/{product_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Image Pending Product image unavailable", response.data)
        self.assertIn(b"Out of stock", response.data)

    def test_shared_footer_is_used_on_storefront_information_pages(self):
        for path in ("/about", "/contact", "/learn", "/privacy"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'class="premium-footer"', response.data)
                self.assertIn(b'href="/privacy"', response.data)

        contact = self.client.get("/contact")
        self.assertIn(b"Direct contact details are not currently published.", contact.data)
        self.assertNotIn(b"/submit-contact-form", contact.data)

    def test_product_image_upload_is_normalized_and_ignores_client_filename(self):
        self.sign_in()
        response = self.client.post(
            "/admin/products",
            data=self.product_form(image=(image_file(), "..\\..\\public.png")),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            product = Product.query.filter_by(slug="calming-daily-lotion").one()
            self.assertRegex(product.image_key, r"^products/[a-f0-9]{32}\.webp$")
            stored_data = self.storage.files[product.image_key]
        with Image.open(io.BytesIO(stored_data)) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (40, 60))

    def test_upload_without_storage_fails_clearly_without_losing_product(self):
        self.sign_in()
        self.app.extensions["product_image_storage"] = None

        response = self.client.post(
            "/admin/products",
            data=self.product_form(image=(image_file(), "new.png")),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        products_page = self.client.get("/admin/products")
        self.assertIn(b"Product image storage is not configured", products_page.data)
        with self.app.app_context():
            self.assertEqual(Product.query.count(), 4)

    def test_failed_replacement_preserves_product_and_existing_image(self):
        self.sign_in()
        with self.app.app_context():
            product = db.session.get(Product, 1)
            product.name = "Existing Product Name"
            product.image_key = "products/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.webp"
            db.session.commit()
            self.storage.files[product.image_key] = b"existing image"
            product_id = product.id
            old_key = product.image_key
        self.storage.fail_save = True

        response = self.client.post(
            f"/admin/products/{product_id}/edit",
            data=self.product_form(name="Changed Name", image=(image_file(), "new.png")),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            product = db.session.get(Product, product_id)
            self.assertEqual(product.name, "Existing Product Name")
            self.assertEqual(product.image_key, old_key)
            self.assertIn(old_key, self.storage.files)

    def test_replacing_existing_uploaded_image_commits_before_old_file_cleanup(self):
        self.sign_in()
        old_key = "products/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.webp"
        self.storage.files[old_key] = b"old image"
        with self.app.app_context():
            product = db.session.get(Product, 1)
            product.image_key = old_key
            db.session.commit()
            product_id = product.id

        response = self.client.post(
            f"/admin/products/{product_id}/edit",
            data=self.product_form(image=(image_file("JPEG"), "replacement.jpg")),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            product = db.session.get(Product, product_id)
            self.assertNotEqual(product.image_key, old_key)
            self.assertRegex(product.image_key, r"^products/[a-f0-9]{32}\.webp$")
            self.assertNotIn(old_key, self.storage.files)
            self.assertIn(product.image_key, self.storage.files)

    def test_failed_image_delete_clears_database_reference_and_reports_warning(self):
        self.sign_in()
        image_key = "products/cccccccccccccccccccccccccccccccc.webp"
        self.storage.files[image_key] = b"stored image"
        with self.app.app_context():
            product = db.session.get(Product, 1)
            product.image_key = image_key
            db.session.commit()
            product_id = product.id
        self.storage.fail_delete = True

        response = self.client.post(
            f"/admin/products/{product_id}/edit",
            data={"csrf_token": self.csrf_token(), "image_action": "remove"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Product, product_id).image_key)
        self.assertIn(b"could not be cleaned up", self.client.get("/admin/products").data)
        self.assertIn(image_key, self.storage.files)

    def test_successful_image_removal_clears_reference_and_deletes_file(self):
        self.sign_in()
        image_key = "products/dddddddddddddddddddddddddddddddd.webp"
        self.storage.files[image_key] = b"stored image"
        with self.app.app_context():
            product = db.session.get(Product, 1)
            product.image_key = image_key
            db.session.commit()
            product_id = product.id

        response = self.client.post(
            f"/admin/products/{product_id}/edit",
            data={"csrf_token": self.csrf_token(), "image_action": "remove"},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(Product, product_id).image_key)
        self.assertNotIn(image_key, self.storage.files)

    def test_admin_product_management_remains_authenticated_and_csrf_protected(self):
        response = self.client.get("/admin/products")
        self.assertEqual(response.status_code, 302)
        self.sign_in()
        response = self.client.post("/admin/products", data=self.product_form(csrf_token=""))
        self.assertEqual(response.status_code, 400)

    def test_product_images_require_complete_storage_configuration(self):
        self.assertIsNone(create_product_image_storage({}))
        storage = create_product_image_storage(
            {
                "PRODUCT_IMAGE_STORAGE_BUCKET": "public-products",
                "PRODUCT_IMAGE_STORAGE_REGION": "test-region",
                "PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID": "test-access",
                "PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY": "test-secret",
                "PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL": "https://cdn.example.test/assets",
                "PRODUCT_IMAGE_STORAGE_ENDPOINT_URL": "https://s3.example.test",
            }
        )
        self.assertEqual(
            storage.public_url("products/0123456789abcdef0123456789abcdef.webp"),
            "https://cdn.example.test/assets/products/0123456789abcdef0123456789abcdef.webp",
        )
        self.assertIsNone(storage.public_url("../receipts/forbidden.png"))

        with self.assertRaisesRegex(RuntimeError, "public HTTPS URL"):
            create_product_image_storage(
                {
                    "PRODUCT_IMAGE_STORAGE_BUCKET": "public-products",
                    "PRODUCT_IMAGE_STORAGE_REGION": "test-region",
                    "PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID": "test-access",
                    "PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY": "test-secret",
                    "PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL": "http://images.example.test",
                }
            )

    def test_image_validation_rejects_bad_formats_dimensions_and_oversize(self):
        valid = FileStorage(stream=image_file(), filename="valid.png")
        normalized = validate_product_image(valid, 1024 * 1024)
        with Image.open(io.BytesIO(normalized)) as image:
            self.assertEqual(image.format, "WEBP")

        unsupported = FileStorage(stream=image_file("GIF"), filename="animated.gif")
        with self.assertRaisesRegex(ProductImageError, "JPEG, PNG, or WebP"):
            validate_product_image(unsupported, 1024 * 1024)

        oversized_dimensions = FileStorage(
            stream=image_file(size=(MAX_IMAGE_DIMENSION + 1, 1)),
            filename="wide.png",
        )
        with self.assertRaisesRegex(ProductImageError, "dimensions are too large"):
            validate_product_image(oversized_dimensions, 1024 * 1024)

        too_large = FileStorage(stream=io.BytesIO(b"x" * 8), filename="large.png")
        with self.assertRaisesRegex(ProductImageError, "4 MB or smaller"):
            validate_product_image(too_large, 4)

        corrupt = FileStorage(stream=io.BytesIO(b"not an image"), filename="bad.png")
        with self.assertRaisesRegex(ProductImageError, "not a valid"):
            validate_product_image(corrupt, 1024 * 1024)

    def test_footer_only_displays_configured_https_social_links(self):
        response = self.client.get("/")
        self.assertNotIn(b"aria-label=\"Social media\"", response.data)

        with patch(
            "app.app.FOOTER_SOCIAL_LINKS",
            (("Instagram", "https://instagram.example.test/brand"),),
        ):
            response = self.client.get("/")
        self.assertIn(b'href="https://instagram.example.test/brand"', response.data)
        self.assertIn(b"rel=\"noopener noreferrer\"", response.data)


if __name__ == "__main__":
    unittest.main()
