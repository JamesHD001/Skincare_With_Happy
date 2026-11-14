from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import BytesIO
from pathlib import Path

import click
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_migrate import Migrate
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from app.config import (
        ADMIN_PASSWORD,
        ADMIN_USERNAME,
        APP_ENV,
        DATABASE_URL,
        DIRECT_DATABASE_URL,
        FOOTER_CONTACT_EMAIL,
        FOOTER_CONTACT_PHONE,
        FOOTER_SOCIAL_LINKS,
        MAX_RECEIPT_SIZE_BYTES,
        MAX_PRODUCT_IMAGE_SIZE_BYTES,
        PAYSTACK_PUBLIC_KEY,
        PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID,
        PRODUCT_IMAGE_STORAGE_BUCKET,
        PRODUCT_IMAGE_STORAGE_ENDPOINT_URL,
        PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL,
        PRODUCT_IMAGE_STORAGE_REGION,
        PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY,
        RECEIPT_STORAGE_ACCESS_KEY_ID,
        RECEIPT_STORAGE_BUCKET,
        RECEIPT_STORAGE_ENDPOINT_URL,
        RECEIPT_STORAGE_REGION,
        RECEIPT_STORAGE_SECRET_ACCESS_KEY,
        SECRET_KEY,
        SQLALCHEMY_DATABASE_URI,
    )
    from app.models import AdminProfile, Customer, Order, OrderItem, PaymentAuditLog, Product, db
    from app.receipt_storage import (
        ReceiptNotFound,
        ReceiptStorageError,
        create_receipt_storage,
    )
    from app.product_image_storage import (
        ProductImageError,
        ProductImageStorageError,
        create_product_image_storage,
        validate_product_image,
    )
except ImportError:  # pragma: no cover - compatibility for direct script execution
    from config import (
        ADMIN_PASSWORD,
        ADMIN_USERNAME,
        APP_ENV,
        DATABASE_URL,
        DIRECT_DATABASE_URL,
        FOOTER_CONTACT_EMAIL,
        FOOTER_CONTACT_PHONE,
        FOOTER_SOCIAL_LINKS,
        MAX_RECEIPT_SIZE_BYTES,
        MAX_PRODUCT_IMAGE_SIZE_BYTES,
        PAYSTACK_PUBLIC_KEY,
        PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID,
        PRODUCT_IMAGE_STORAGE_BUCKET,
        PRODUCT_IMAGE_STORAGE_ENDPOINT_URL,
        PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL,
        PRODUCT_IMAGE_STORAGE_REGION,
        PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY,
        RECEIPT_STORAGE_ACCESS_KEY_ID,
        RECEIPT_STORAGE_BUCKET,
        RECEIPT_STORAGE_ENDPOINT_URL,
        RECEIPT_STORAGE_REGION,
        RECEIPT_STORAGE_SECRET_ACCESS_KEY,
        SECRET_KEY,
        SQLALCHEMY_DATABASE_URI,
    )
    from models import AdminProfile, Customer, Order, OrderItem, PaymentAuditLog, Product, db
    from receipt_storage import (
        ReceiptNotFound,
        ReceiptStorageError,
        create_receipt_storage,
    )
    from product_image_storage import (
        ProductImageError,
        ProductImageStorageError,
        create_product_image_storage,
        validate_product_image,
    )


BASE_DIR = Path(__file__).resolve().parent.parent
MAX_CART_LINES = 20
MAX_ITEM_QUANTITY = 20
ALLOWED_PAYMENT_METHODS = {"manual_transfer", "bank_transfer", "opay"}
BUILT_IN_PRODUCT_IMAGES = {
    "niacinamide-balancing-serum": "builtin/niacinamide-balancing-serum.svg",
    "gentle-cream-cleanser": "builtin/gentle-cream-cleanser.svg",
    "vitamin-c-glow-essence": "builtin/vitamin-c-glow-essence.svg",
    "hydrating-barrier-cream": "builtin/hydrating-barrier-cream.svg",
}
RECEIPT_FORMATS = {
    ".png": ("png", "image/png"),
    ".jpg": ("jpeg", "image/jpeg"),
    ".jpeg": ("jpeg", "image/jpeg"),
    ".webp": ("webp", "image/webp"),
    ".pdf": ("pdf", "application/pdf"),
}


def seed_products():
    products = [
        {
            "name": "Niacinamide Balancing Serum",
            "slug": "niacinamide-balancing-serum",
            "skin_type": "oily",
            "price": Decimal("30.00"),
            "description": "Lightweight serum for oily and combination skin.",
            "stock": 25,
            "image_key": BUILT_IN_PRODUCT_IMAGES["niacinamide-balancing-serum"],
        },
        {
            "name": "Gentle Cream Cleanser",
            "slug": "gentle-cream-cleanser",
            "skin_type": "dry",
            "price": Decimal("18.00"),
            "description": "Comforting cleanser for normal to dry skin.",
            "stock": 30,
            "image_key": BUILT_IN_PRODUCT_IMAGES["gentle-cream-cleanser"],
        },
        {
            "name": "Vitamin C Glow Essence",
            "slug": "vitamin-c-glow-essence",
            "skin_type": "all",
            "price": Decimal("28.00"),
            "description": "Brightening treatment to support an even-looking glow.",
            "stock": 20,
            "image_key": BUILT_IN_PRODUCT_IMAGES["vitamin-c-glow-essence"],
        },
        {
            "name": "Hydrating Barrier Cream",
            "slug": "hydrating-barrier-cream",
            "skin_type": "dry",
            "price": Decimal("34.00"),
            "description": "Deep hydration to reinforce the skin barrier.",
            "stock": 18,
            "image_key": BUILT_IN_PRODUCT_IMAGES["hydrating-barrier-cream"],
        },
    ]

    added = 0
    for payload in products:
        if Product.query.filter_by(slug=payload["slug"]).first() is None:
            db.session.add(Product(**payload))
            added += 1

    db.session.commit()
    return added


class CartValidationError(ValueError):
    pass


class CheckoutError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def parse_cart(cart):
    if isinstance(cart, str):
        try:
            cart = json.loads(cart)
        except (TypeError, ValueError) as error:
            raise CartValidationError("Your cart is invalid. Review it and try again.") from error
    if not isinstance(cart, list) or not cart:
        raise CartValidationError("Your cart is empty.")
    if len(cart) > MAX_CART_LINES:
        raise CartValidationError(f"A cart can contain at most {MAX_CART_LINES} products.")

    quantities = {}
    for entry in cart:
        if not isinstance(entry, dict):
            raise CartValidationError("Your cart contains an invalid product.")
        product_id = entry.get("product_id")
        quantity = entry.get("quantity")
        if isinstance(product_id, bool) or not (
            isinstance(product_id, int)
            or isinstance(product_id, str) and product_id.isdecimal()
        ):
            raise CartValidationError("Your cart contains an invalid product.")
        if isinstance(quantity, bool) or not (
            isinstance(quantity, int)
            or isinstance(quantity, str) and quantity.isdecimal()
        ):
            raise CartValidationError("Product quantities must be whole numbers.")
        product_id = int(product_id)
        quantity = int(quantity)
        if product_id < 1:
            raise CartValidationError("Your cart contains an invalid product.")
        if quantity < 1 or quantity > MAX_ITEM_QUANTITY:
            raise CartValidationError(
                f"Each product quantity must be between 1 and {MAX_ITEM_QUANTITY}."
            )
        quantities[product_id] = quantities.get(product_id, 0) + quantity
        if quantities[product_id] > MAX_ITEM_QUANTITY:
            raise CartValidationError(
                f"Each product quantity must be between 1 and {MAX_ITEM_QUANTITY}."
            )
    return [
        {"product_id": product_id, "quantity": quantity}
        for product_id, quantity in sorted(quantities.items())
    ]


def build_cart_summary(cart):
    items = []
    subtotal = Decimal("0.00")
    try:
        parsed_cart = parse_cart(cart)
    except CartValidationError as error:
        return {
            "items": [],
            "subtotal": subtotal,
            "total": subtotal,
            "error": str(error),
            "available": False,
        }

    product_ids = [entry["product_id"] for entry in parsed_cart]
    products = {
        product.id: product
        for product in Product.query.filter(Product.id.in_(product_ids)).all()
    }

    for entry in parsed_cart:
        product_id = entry["product_id"]
        quantity = entry["quantity"]
        product = products.get(product_id)
        available = product is not None and product.stock >= quantity and product.stock > 0
        price = product.price if product is not None else Decimal("0.00")
        line_total = price * quantity
        if product is not None:
            subtotal += line_total
        items.append(
            {
                "product_id": product_id,
                "name": product.name if product is not None else "Unavailable product",
                "price": price,
                "quantity": quantity,
                "line_total": line_total,
                "stock": product.stock if product is not None else 0,
                "available": available,
            }
        )

    return {
        "items": items,
        "subtotal": subtotal,
        "total": subtotal,
        "available": all(item["available"] for item in items),
        "error": None,
    }


def validate_receipt_upload(file_storage, max_bytes):
    if file_storage is None or not file_storage.filename:
        raise CheckoutError("Upload a payment receipt.")
    filename = file_storage.filename
    if "/" in filename or "\\" in filename or Path(filename).name != filename:
        raise CheckoutError("The receipt filename is invalid.")

    suffix = Path(filename).suffix.lower()
    receipt_format = RECEIPT_FORMATS.get(suffix)
    if receipt_format is None:
        raise CheckoutError("Upload a PNG, JPEG, WebP image, or PDF receipt.")

    data = file_storage.stream.read(max_bytes + 1)
    if not data:
        raise CheckoutError("The uploaded receipt is empty.")
    if len(data) > max_bytes:
        raise CheckoutError("Receipt files must be 5 MB or smaller.")

    expected_format, content_type = receipt_format
    if expected_format == "pdf":
        try:
            reader = PdfReader(BytesIO(data), strict=True)
            if reader.is_encrypted or not reader.pages or len(reader.pages) > 100:
                raise CheckoutError("Upload a readable, unencrypted PDF with no more than 100 pages.")
        except (PdfReadError, ValueError, OSError) as error:
            raise CheckoutError("The uploaded PDF is invalid or unreadable.") from error
        extension = "pdf"
    else:
        try:
            with Image.open(BytesIO(data)) as image:
                actual_format = (image.format or "").lower()
                if actual_format != expected_format:
                    raise CheckoutError("The receipt extension does not match its image format.")
                if image.width * image.height > 20_000_000:
                    raise CheckoutError("The receipt image dimensions are too large.")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise CheckoutError("The uploaded image is invalid or unreadable.") from error
        extension = "jpg" if expected_format == "jpeg" else expected_format

    return data, extension, content_type


def make_product_slug(name, product_id=None):
    base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "product"
    slug = base_slug
    suffix = 2

    while True:
        query = Product.query.filter_by(slug=slug)
        if product_id is not None:
            query = query.filter(Product.id != product_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


def parse_product_form(form):
    name = form.get("name", "").strip()
    skin_type = form.get("skin_type", "").strip().lower()
    description = form.get("description", "").strip()

    if not name:
        return None, "Product name is required."
    if skin_type not in {"all", "oily", "dry", "combination", "normal", "sensitive"}:
        return None, "Choose a valid skin type."

    try:
        price = Decimal(form.get("price", "").strip())
        stock = int(form.get("stock", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None, "Enter a valid price and whole-number stock quantity."

    if not price.is_finite() or price <= 0:
        return None, "Price must be a positive number."
    if price >= Decimal("1000000000000"):
        return None, "Price exceeds the supported NGN amount."
    if price != price.quantize(Decimal("0.01")):
        return None, "Price must use no more than two decimal places."
    if stock < 0:
        return None, "Stock cannot be negative."

    return {
        "name": name,
        "skin_type": skin_type,
        "price": price,
        "stock": stock,
        "description": description,
    }, None


def create_app():
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = APP_ENV == "production"
    app.config["MAX_CONTENT_LENGTH"] = MAX_RECEIPT_SIZE_BYTES + 64 * 1024
    app.config["MAX_PRODUCT_IMAGE_SIZE_BYTES"] = MAX_PRODUCT_IMAGE_SIZE_BYTES
    app.config["RECEIPT_STORAGE_BUCKET"] = RECEIPT_STORAGE_BUCKET
    app.config["RECEIPT_STORAGE_REGION"] = RECEIPT_STORAGE_REGION
    app.config["RECEIPT_STORAGE_ENDPOINT_URL"] = RECEIPT_STORAGE_ENDPOINT_URL
    app.config["RECEIPT_STORAGE_ACCESS_KEY_ID"] = RECEIPT_STORAGE_ACCESS_KEY_ID
    app.config["RECEIPT_STORAGE_SECRET_ACCESS_KEY"] = RECEIPT_STORAGE_SECRET_ACCESS_KEY
    app.config["PRODUCT_IMAGE_STORAGE_BUCKET"] = PRODUCT_IMAGE_STORAGE_BUCKET
    app.config["PRODUCT_IMAGE_STORAGE_REGION"] = PRODUCT_IMAGE_STORAGE_REGION
    app.config["PRODUCT_IMAGE_STORAGE_ENDPOINT_URL"] = PRODUCT_IMAGE_STORAGE_ENDPOINT_URL
    app.config["PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID"] = PRODUCT_IMAGE_STORAGE_ACCESS_KEY_ID
    app.config["PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY"] = PRODUCT_IMAGE_STORAGE_SECRET_ACCESS_KEY
    app.config["PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL"] = PRODUCT_IMAGE_STORAGE_PUBLIC_BASE_URL
    app.extensions["receipt_storage"] = create_receipt_storage(app.config)
    app.extensions["product_image_storage"] = create_product_image_storage(app.config)

    db.init_app(app)
    Migrate(app, db)

    def get_admin_profile():
        if not ADMIN_USERNAME:
            return None
        return AdminProfile.query.filter_by(username=ADMIN_USERNAME).first()

    def get_or_create_admin_profile():
        profile = get_admin_profile()
        if profile is None:
            profile = AdminProfile(username=ADMIN_USERNAME, display_name=ADMIN_USERNAME)
            db.session.add(profile)
            db.session.flush()
        return profile

    def verify_admin_password(profile, password):
        if profile and profile.password_hash:
            return check_password_hash(profile.password_hash, password)
        return bool(ADMIN_PASSWORD) and hmac.compare_digest(
            password.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")
        )

    def clear_admin_session():
        session.pop("admin_authenticated", None)
        session.pop("admin_username", None)
        session.pop("admin_credential_version", None)
        session["admin_csrf_token"] = secrets.token_urlsafe(32)

    def admin_credential_version():
        profile = get_admin_profile()
        password_material = profile.password_hash if profile and profile.password_hash else ADMIN_PASSWORD
        credentials = f"{ADMIN_USERNAME}\0{password_material}".encode("utf-8")
        return hmac.new(SECRET_KEY.encode("utf-8"), credentials, hashlib.sha256).hexdigest()

    def is_admin_authenticated():
        profile = get_admin_profile()
        configured = bool(ADMIN_USERNAME and (ADMIN_PASSWORD or (profile and profile.password_hash)))
        stored_version = session.get("admin_credential_version", "")
        return (
            configured
            and session.get("admin_authenticated") is True
            and hmac.compare_digest(stored_version, admin_credential_version())
        )

    def admin_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("admin_authenticated") is True and not is_admin_authenticated():
                clear_admin_session()
            if not is_admin_authenticated():
                return redirect(url_for("admin_login"))
            return view(*args, **kwargs)

        return wrapped_view

    def clear_customer_session():
        session.pop("customer_id", None)
        session.pop("customer_name", None)
        session["customer_csrf_token"] = secrets.token_urlsafe(32)

    def product_image_url(image_key):
        if not image_key:
            return None
        for slug, built_in_key in BUILT_IN_PRODUCT_IMAGES.items():
            if image_key == built_in_key:
                return url_for("static", filename=f"img/products/{slug}.svg")
        storage = app.extensions.get("product_image_storage")
        return storage.public_url(image_key) if storage is not None else None

    def store_uploaded_product_image():
        image_file = request.files.get("image")
        if image_file is None or not image_file.filename:
            return None, None
        try:
            image_data = validate_product_image(
                image_file, app.config["MAX_PRODUCT_IMAGE_SIZE_BYTES"]
            )
        except ProductImageError as error:
            return None, str(error)

        storage = app.extensions.get("product_image_storage")
        if storage is None:
            return None, (
                "Product image storage is not configured. Configure the separate "
                "public product-image bucket before uploading."
            )
        try:
            return storage.save(image_data), None
        except ProductImageStorageError:
            app.logger.warning("Product image upload failed.")
            return None, "Product image storage is temporarily unavailable."

    def available_product_skin_types():
        return [
            skin_type
            for (skin_type,) in (
                db.session.query(Product.skin_type)
                .distinct()
                .order_by(Product.skin_type)
                .all()
            )
            if skin_type
        ]

    def cleanup_uploaded_product_image(storage, image_key):
        if storage is None or not image_key:
            return
        try:
            storage.delete(image_key)
        except ProductImageStorageError:
            app.logger.warning("Unable to clean up an unused product image.")

    def get_current_customer():
        customer_id = session.get("customer_id")
        if customer_id is None:
            return None

        try:
            customer_id = int(customer_id)
        except (TypeError, ValueError):
            clear_customer_session()
            return None

        customer = db.session.get(Customer, customer_id)
        if customer is None:
            clear_customer_session()
        return customer

    def customer_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            customer = get_current_customer()
            if customer is None:
                return redirect(url_for("signin"))
            return view(customer, *args, **kwargs)

        return wrapped_view

    @app.context_processor
    def inject_year():
        csrf_token = session.get("admin_csrf_token", "")
        if request.path.startswith("/admin") and not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            session["admin_csrf_token"] = csrf_token
        customer_csrf_token = session.get("customer_csrf_token", "")
        if (
            request.path in {"/", "/signup", "/signin", "/account", "/checkout", "/cart", "/shop", "/products"}
            or request.path.startswith("/product/")
            or request.path.startswith("/cart/")
        ) and not customer_csrf_token:
            customer_csrf_token = secrets.token_urlsafe(32)
            session["customer_csrf_token"] = customer_csrf_token
        admin_profile = get_admin_profile() if session.get("admin_authenticated") is True else None
        return {
            "current_year": datetime.now().year,
            "cart_count": sum(item.get("quantity", 0) for item in session.get("cart", []) if isinstance(item, dict) and isinstance(item.get("quantity"), int)),
            "admin_csrf_token": csrf_token,
            "customer_csrf_token": customer_csrf_token,
            "admin_profile": admin_profile,
            "product_image_url": product_image_url,
            "footer_social_links": FOOTER_SOCIAL_LINKS,
            "footer_contact_email": FOOTER_CONTACT_EMAIL,
            "footer_contact_phone": FOOTER_CONTACT_PHONE,
        }

    @app.template_filter("naira")
    def format_naira(amount):
        value = Decimal(str(amount or "0")).quantize(Decimal("0.01"))
        return f"₦{value:,.2f}"

    @app.before_request
    def validate_admin_csrf():
        if request.method == "POST" and request.path.startswith("/admin"):
            expected_token = session.get("admin_csrf_token", "")
            submitted_token = request.form.get("csrf_token", "")
            if not expected_token or not submitted_token or not hmac.compare_digest(
                expected_token, submitted_token
            ):
                abort(400, description="The form expired or its security token is invalid. Reload and try again.")
        elif request.method == "POST" and (
            request.path in {"/signup", "/signin", "/signout", "/checkout"}
            or request.path.startswith("/cart/")
        ):
            expected_token = session.get("customer_csrf_token", "")
            json_payload = request.get_json(silent=True) if request.is_json else None
            json_token = json_payload.get("csrf_token", "") if isinstance(json_payload, dict) else ""
            submitted_token = (
                request.form.get("csrf_token", "")
                or request.headers.get("X-CSRF-Token", "")
                or json_token
            )
            if not expected_token or not isinstance(submitted_token, str) or not submitted_token or not hmac.compare_digest(
                expected_token, submitted_token
            ):
                abort(400, description="The form expired or its security token is invalid. Reload and try again.")

    @app.before_request
    def hide_legacy_public_receipts():
        if request.path.startswith("/static/uploads/payments/"):
            abort(404)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_upload(error):
        if request.path == "/checkout":
            return jsonify({"status": "error", "message": "Receipt files must be 5 MB or smaller."}), 413
        if request.path == "/admin/products" or request.path.startswith("/admin/products/"):
            flash("Product images must be 4 MB or smaller.", "error")
            return redirect(url_for("admin_products"))
        return error

    @app.cli.command("seed-products")
    def seed_products_command():
        try:
            added = seed_products()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Product seeding failed.")
            raise
        click.echo(f"Seeded {added} product(s).")

    @app.route("/")
    def index():
        products = Product.query.order_by(Product.id).all()
        return render_template("index.html", products=products)

    @app.route("/shop")
    def shop():
        skin_type = request.args.get("type", "").strip().lower()
        query = Product.query
        if skin_type:
            allowed_skin_types = {"all", "oily", "dry", "combination", "normal", "sensitive"}
            if skin_type not in allowed_skin_types:
                abort(404)
            if skin_type == "all":
                query = query.filter(Product.skin_type == "all")
            else:
                query = query.filter(or_(Product.skin_type == skin_type, Product.skin_type == "all"))
        return render_template(
            "shop.html",
            products=query.order_by(Product.id).all(),
            skin_type=skin_type,
            skin_types=available_product_skin_types(),
        )

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/learn")
    def learn():
        return render_template("learn.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if get_current_customer() is not None:
            return redirect(url_for("account"))

        form_data = {
            "full_name": request.form.get("full_name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone_number": request.form.get("phone_number", "").strip(),
        }
        if request.method == "POST":
            password = request.form.get("password", "")
            email = form_data["email"].lower()

            if not form_data["full_name"] or len(form_data["full_name"]) > 150:
                flash("Enter your name (150 characters or fewer).", "error")
            elif len(email) > 254:
                flash("Email address must be 254 characters or fewer.", "error")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid email address.", "error")
            elif len(form_data["phone_number"]) > 40:
                flash("Phone number must be 40 characters or fewer.", "error")
            elif len(password) < 12:
                flash("Choose a password with at least 12 characters.", "error")
            elif len(password) > 256:
                flash("Password must be 256 characters or fewer.", "error")
            elif Customer.query.filter(func.lower(Customer.email) == email).first():
                flash("An account with that email already exists. Sign in instead.", "error")
            else:
                customer = Customer(
                    full_name=form_data["full_name"],
                    email=email,
                    phone_number=form_data["phone_number"] or None,
                    password_hash=generate_password_hash(password),
                )
                db.session.add(customer)
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("An account with that email already exists. Sign in instead.", "error")
                else:
                    clear_customer_session()
                    session["customer_id"] = customer.id
                    session["customer_name"] = customer.full_name
                    flash("Your account is ready. Welcome to Skincare With Happy!", "success")
                    return redirect(url_for("account"))

        return render_template("signup.html", form_data=form_data)

    @app.route("/signin", methods=["GET", "POST"])
    def signin():
        if get_current_customer() is not None:
            return redirect(url_for("account"))

        email = request.form.get("email", "").strip().lower()
        if request.method == "POST":
            customer = Customer.query.filter_by(email=email).first()
            password = request.form.get("password", "")
            if customer is None or not check_password_hash(customer.password_hash, password):
                flash("Email or password is incorrect.", "error")
            else:
                clear_customer_session()
                session["customer_id"] = customer.id
                session["customer_name"] = customer.full_name
                flash(f"Welcome back, {customer.full_name}.", "success")
                return redirect(url_for("account"))

        return render_template("signin.html", email=email)

    @app.route("/signout", methods=["POST"])
    def signout():
        if get_current_customer() is None:
            return redirect(url_for("signin"))
        clear_customer_session()
        flash("You have been signed out.", "success")
        return redirect(url_for("index"))

    @app.route("/account")
    @customer_required
    def account(customer):
        orders = (
            Order.query.filter_by(customer_id=customer.id)
            .order_by(Order.created_at.desc())
            .all()
        )
        return render_template("account.html", customer=customer, orders=orders)

    @app.route("/skin-quiz")
    def skin_quiz():
        return render_template("skin_quiz.html")

    @app.route("/products")
    def products():
        skin_type = request.args.get("type", "").strip().lower()
        query = Product.query
        if skin_type:
            query = query.filter(Product.skin_type == skin_type)
        return render_template(
            "products.html",
            products=query.order_by(Product.id).all(),
            skin_type=skin_type,
            skin_types=available_product_skin_types(),
        )

    @app.route("/product/<int:product_id>")
    def product_detail(product_id):
        product = Product.query.get_or_404(product_id)
        return render_template("product_details.html", product=product, PAYSTACK_PUBLIC_KEY=PAYSTACK_PUBLIC_KEY)

    @app.route("/cart")
    def cart():
        cart_summary = build_cart_summary(session.get("cart", []))
        return render_template(
            "cart.html",
            cart_summary=cart_summary,
            PAYSTACK_PUBLIC_KEY=PAYSTACK_PUBLIC_KEY,
        )

    @app.route("/cart/add", methods=["POST"])
    def add_to_cart():
        try:
            parsed = parse_cart(
                [{"product_id": request.form.get("product_id"), "quantity": request.form.get("quantity", "1")}]
            )
        except CartValidationError as error:
            flash(str(error), "error")
            return redirect(url_for("shop"))
        product_id = parsed[0]["product_id"]
        quantity = parsed[0]["quantity"]
        product = Product.query.get_or_404(product_id)
        if product.stock < quantity:
            flash("The requested quantity is not currently in stock.", "error")
            return redirect(url_for("product_detail", product_id=product_id))

        cart = session.get("cart", [])
        try:
            cart = parse_cart(cart) if cart else []
            updated = parse_cart(
                cart + [{"product_id": product.id, "quantity": quantity}]
            )
        except CartValidationError as error:
            flash(str(error), "error")
            return redirect(url_for("cart"))
        if not any(item["product_id"] == product_id for item in updated):
            flash("Your cart could not be updated.", "error")
            return redirect(url_for("cart"))
        item = next(item for item in updated if item["product_id"] == product_id)
        if item["quantity"] > product.stock:
            flash("The requested quantity is not currently in stock.", "error")
            return redirect(url_for("cart"))
        if len(updated) > MAX_CART_LINES:
            flash(f"A cart can contain at most {MAX_CART_LINES} products.", "error")
            return redirect(url_for("cart"))
        session["cart"] = updated
        cart_count = sum(entry["quantity"] for entry in updated)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "success", "message": "Product added to your cart.", "cart_count": cart_count, "cart_url": url_for("cart")})
        return redirect(url_for("cart"))

    @app.route("/cart/update", methods=["POST"])
    def update_cart():
        try:
            cart = parse_cart(session.get("cart", []))
            updated = parse_cart([
                {
                    "product_id": item["product_id"],
                    "quantity": request.form.get(
                        f"quantity_{item['product_id']}", str(item["quantity"])
                    ),
                }
                for item in cart
            ])
        except CartValidationError as error:
            flash(str(error), "error")
            return redirect(url_for("cart"))
        session["cart"] = updated
        return redirect(url_for("cart"))

    @app.route("/cart/remove/<int:product_id>", methods=["POST"])
    def remove_from_cart(product_id):
        cart = session.get("cart", [])
        try:
            cart = parse_cart(cart) if cart else []
        except CartValidationError:
            cart = []
        session["cart"] = [
            item for item in cart if item["product_id"] != product_id
        ]
        return redirect(url_for("cart"))

    @app.route("/checkout", methods=["GET", "POST"])
    def checkout():
        if request.method == "GET":
            cart_summary = build_cart_summary(session.get("cart", []))
            return render_template(
                "checkout.html",
                cart_summary=cart_summary,
                customer=get_current_customer(),
            )

        if request.is_json:
            return jsonify({
                "status": "error",
                "message": "Checkout requires a multipart receipt upload.",
            }), 415
        payload = request.form
        try:
            cart = parse_cart(session.get("cart", []))
        except CartValidationError as error:
            return jsonify({"status": "error", "message": str(error)}), 400

        customer = get_current_customer()
        if customer is None:
            email = (payload.get("email") or "").strip().lower()
            name = (payload.get("name") or payload.get("customer_name") or "").strip()
            phone = (payload.get("phone") or payload.get("phone_number") or "").strip()
        else:
            email = customer.email
            name = customer.full_name
            phone = (
                (payload.get("phone") or payload.get("phone_number") or "").strip()
                or customer.phone_number
                or ""
            )
        payment_method = (payload.get("payment_method") or "manual_transfer").strip().lower()
        payment_reference = (payload.get("reference") or payload.get("transaction_reference") or "").strip()

        if not name or len(name) > 150:
            return jsonify({"status": "error", "message": "Enter a valid customer name."}), 400
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
            return jsonify({"status": "error", "message": "Enter a valid customer email address."}), 400
        if len(phone) > 40:
            return jsonify({"status": "error", "message": "Phone number must be 40 characters or fewer."}), 400
        if payment_method not in ALLOWED_PAYMENT_METHODS:
            return jsonify({"status": "error", "message": "Choose a supported payment method."}), 400
        if not payment_reference or len(payment_reference) > 120:
            return jsonify({"status": "error", "message": "A payment reference is required for the selected payment method."}), 400

        if payment_reference and Order.query.filter_by(payment_reference=payment_reference).first():
            return jsonify({"status": "error", "message": "This payment reference has already been used."}), 409

        storage = app.extensions.get("receipt_storage")
        if storage is None:
            return jsonify({
                "status": "error",
                "message": "Private receipt storage is not configured. Please try again later.",
            }), 503
        try:
            receipt_data, receipt_extension, receipt_content_type = validate_receipt_upload(
                request.files.get("receipt"), MAX_RECEIPT_SIZE_BYTES
            )
        except CheckoutError as error:
            return jsonify({"status": "error", "message": str(error)}), error.status_code
        try:
            receipt_key = storage.save(
                receipt_data, receipt_extension, receipt_content_type
            )
        except ReceiptStorageError as error:
            app.logger.warning("Private receipt upload failed: %s", error)
            return jsonify({
                "status": "error",
                "message": "Receipt storage is temporarily unavailable. Please try again later.",
            }), 503

        try:
            product_ids = [item["product_id"] for item in cart]
            products = {
                product.id: product
                for product in Product.query.filter(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
                .all()
            }
            if len(products) != len(product_ids):
                raise CheckoutError("A product in your cart is no longer available.", 409)

            total = Decimal("0.00")
            for item in cart:
                product = products[item["product_id"]]
                if product.stock < item["quantity"]:
                    raise CheckoutError(
                        f"Only {product.stock} unit(s) of {product.name} remain in stock.",
                        409,
                    )
                result = db.session.execute(
                    update(Product)
                    .where(
                        Product.id == product.id,
                        Product.stock >= item["quantity"],
                    )
                    .values(stock=Product.stock - item["quantity"])
                )
                if result.rowcount != 1:
                    raise CheckoutError(
                        f"Only {product.stock} unit(s) of {product.name} remain in stock.",
                        409,
                    )
                total += product.price * item["quantity"]

            order = Order(
                customer_id=customer.id if customer else None,
                customer_name=name,
                user_email=email,
                phone_number=phone or None,
                total_amount=total,
                inventory_deducted=True,
                payment_method=payment_method,
                payment_status="awaiting_verification",
                fulfillment_status="pending",
                payment_reference=payment_reference,
                receipt_file=receipt_key,
            )
            db.session.add(order)
            db.session.flush()

            for item in cart:
                product = products[item["product_id"]]
                db.session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        quantity=item["quantity"],
                        unit_price=product.price,
                    )
                )
            db.session.add(
                PaymentAuditLog(
                    order_id=order.id,
                    event="order_created",
                    details=f"Order created with {payment_method} payment method.",
                    actor="customer",
                )
            )
            db.session.commit()
        except CheckoutError as error:
            db.session.rollback()
            try:
                storage.delete(receipt_key)
            except ReceiptStorageError:
                app.logger.exception("Unable to clean up an unused receipt.")
            return jsonify({"status": "error", "message": str(error)}), error.status_code
        except IntegrityError:
            db.session.rollback()
            try:
                storage.delete(receipt_key)
            except ReceiptStorageError:
                app.logger.exception("Unable to clean up an unused receipt.")
            if Order.query.filter_by(payment_reference=payment_reference).first():
                return jsonify({"status": "error", "message": "This payment reference has already been used."}), 409
            app.logger.exception("Checkout integrity constraint failed.")
            return jsonify({
                "status": "error",
                "message": "The order could not be saved. Please try again.",
            }), 500
        except SQLAlchemyError:
            db.session.rollback()
            try:
                storage.delete(receipt_key)
            except ReceiptStorageError:
                app.logger.exception("Unable to clean up an unused receipt.")
            app.logger.exception("Checkout database transaction failed.")
            return jsonify({
                "status": "error",
                "message": "The order could not be saved. Please try again.",
            }), 500

        session["cart"] = []

        if request.accept_mimetypes.accept_json:
            return jsonify({
                "status": "success",
                "message": "Order submitted for payment verification.",
                "order_id": order.id,
                "payment_status": order.payment_status,
            })

        return redirect(f"/payment?ref={payment_reference}")

    @app.route("/payment")
    def payment_success():
        reference = request.args.get("ref")
        order = Order.query.filter_by(payment_reference=reference).first() if reference else None

        if order is None:
            return render_template("success.html", reference=reference, order=None)

        order_dict = {"items": [], "total": order.total_amount}
        for item in order.items:
            order_dict["items"].append({
                "name": item.product.name,
                "quantity": item.quantity,
                "price": item.unit_price,
            })

        return render_template("success.html", reference=reference, order=order_dict)

    @app.route("/admin/orders/<int:order_id>/receipt")
    @admin_required
    def admin_order_receipt(order_id):
        order = Order.query.get_or_404(order_id)
        if not order.receipt_file:
            abort(404)
        storage = app.extensions.get("receipt_storage")
        if storage is None:
            abort(503, description="Private receipt storage is unavailable.")
        try:
            data = storage.read(order.receipt_file, MAX_RECEIPT_SIZE_BYTES)
        except ReceiptNotFound:
            abort(404)
        except ReceiptStorageError:
            app.logger.exception("Unable to retrieve a private order receipt.")
            abort(503, description="Private receipt storage is unavailable.")

        extension = order.receipt_file.rsplit(".", 1)[-1]
        content_type = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "webp": "image/webp",
            "pdf": "application/pdf",
        }.get(extension)
        if content_type is None:
            abort(404)
        response = send_file(
            BytesIO(data),
            mimetype=content_type,
            as_attachment=True,
            download_name=f"order-{order.id}-receipt.{extension}",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if is_admin_authenticated():
            return redirect(url_for("admin_dashboard"))
        if session.get("admin_authenticated") is True:
            clear_admin_session()

        profile = get_admin_profile()
        configured = bool(ADMIN_USERNAME and (ADMIN_PASSWORD or (profile and profile.password_hash)))
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")

            if not configured:
                flash("Admin login is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD in the environment.", "error")
            elif hmac.compare_digest(username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8")) and verify_admin_password(
                profile, password
            ):
                if profile is None:
                    profile = get_or_create_admin_profile()
                    db.session.commit()
                clear_admin_session()
                session["admin_authenticated"] = True
                session["admin_username"] = ADMIN_USERNAME
                session["admin_credential_version"] = admin_credential_version()
                flash("Welcome back.", "success")
                return redirect(url_for("admin_dashboard"))
            else:
                flash("The username or password is incorrect.", "error")

        return render_template("admin_login.html", configured=configured)

    @app.route("/admin/logout", methods=["POST"])
    @admin_required
    def admin_logout():
        clear_admin_session()
        return redirect(url_for("admin_login"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        paid_revenue = (
            db.session.query(func.coalesce(func.sum(Order.total_amount), Decimal("0.00")))
            .filter(Order.payment_status == "paid")
            .scalar()
        )
        stats = {
            "total_orders": Order.query.count(),
            "awaiting_verification": Order.query.filter(
                Order.payment_status == "awaiting_verification"
            ).count(),
            "paid_revenue": paid_revenue,
            "products": Product.query.count(),
            "low_stock": Product.query.filter(Product.stock <= 5).count(),
        }
        orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
        low_stock_products = Product.query.filter(Product.stock <= 5).order_by(Product.stock.asc()).limit(5).all()
        return render_template(
            "admin_dashboard.html",
            active_page="dashboard",
            orders=orders,
            stats=stats,
            low_stock_products=low_stock_products,
        )

    @app.route("/admin/orders")
    @admin_required
    def admin_orders():
        payment_status = request.args.get("payment_status", "").strip()
        allowed_statuses = {"awaiting_verification", "paid", "rejected", "pending"}
        query = Order.query
        if payment_status:
            if payment_status not in allowed_statuses:
                abort(400, description="Unsupported payment status filter.")
            query = query.filter(Order.payment_status == payment_status)

        orders = query.order_by(Order.created_at.desc()).all()
        return render_template(
            "admin_orders.html",
            active_page="orders",
            orders=orders,
            payment_status=payment_status,
        )

    @app.route("/admin/orders/<int:order_id>/verify", methods=["POST"])
    @admin_required
    def verify_order(order_id):
        order = Order.query.filter_by(id=order_id).with_for_update().first_or_404()
        decision = request.form.get("decision", "").strip().lower()

        if decision not in {"approve", "reject"}:
            abort(400, description="Choose whether to approve or reject the payment.")
        if order.payment_status != "awaiting_verification":
            flash("This payment is no longer awaiting verification.", "error")
            return redirect(url_for("admin_orders"))

        if decision == "approve":
            order.payment_status = "paid"
            order.fulfillment_status = "processing"
            event = "payment_approved"
            details = "Payment manually verified by admin."
        else:
            order.payment_status = "rejected"
            order.fulfillment_status = "payment_issue"
            event = "payment_rejected"
            details = "Payment rejected by admin."
            if order.inventory_deducted:
                for item in order.items:
                    result = db.session.execute(
                        update(Product)
                        .where(Product.id == item.product_id)
                        .values(stock=Product.stock + item.quantity)
                    )
                    if result.rowcount != 1:
                        db.session.rollback()
                        flash("Inventory could not be restored; no order changes were saved.", "error")
                        return redirect(url_for("admin_orders"))
                order.inventory_deducted = False

        db.session.add(
            PaymentAuditLog(
                order_id=order.id,
                event=event,
                details=details,
                actor=session.get("admin_username", "admin"),
            )
        )
        db.session.commit()
        result = "approved" if decision == "approve" else "rejected"
        flash(f"Order #{order.id} payment {result}.", "success")
        return redirect(url_for("admin_orders"))

    @app.route("/admin/products", methods=["GET", "POST"])
    @admin_required
    def admin_products():
        if request.method == "POST":
            values, error = parse_product_form(request.form)
            if error:
                flash(error, "error")
                return redirect(url_for("admin_products"))

            image_key, image_error = store_uploaded_product_image()
            if image_error:
                flash(image_error, "error")
                return redirect(url_for("admin_products"))
            if not image_key:
                flash("A product image is required before adding a product.", "error")
                return redirect(url_for("admin_products"))

            product = Product(
                **values,
                slug=make_product_slug(values["name"]),
                image_key=image_key,
            )
            db.session.add(product)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                cleanup_uploaded_product_image(
                    app.extensions.get("product_image_storage"), image_key
                )
                app.logger.exception("Product creation failed.")
                flash("The product could not be saved. Please try again.", "error")
                return redirect(url_for("admin_products"))
            flash(f"{product.name} was added to the catalog.", "success")
            return redirect(url_for("admin_products"))

        products = Product.query.order_by(Product.name.asc()).all()
        return render_template("admin_products.html", active_page="products", products=products)

    @app.route("/admin/products/<int:product_id>/edit", methods=["POST"])
    @admin_required
    def admin_edit_product(product_id):
        product = Product.query.get_or_404(product_id)
        storage = app.extensions.get("product_image_storage")

        if request.form.get("image_action", "save") == "remove":
            old_image_key = product.image_key
            product.image_key = None
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                app.logger.exception("Product image removal failed.")
                flash("The product image could not be removed. Please try again.", "error")
                return redirect(url_for("admin_products"))

            removal_warning = False
            if old_image_key and old_image_key.startswith("products/"):
                if storage is None:
                    removal_warning = True
                else:
                    try:
                        storage.delete(old_image_key)
                    except ProductImageStorageError:
                        app.logger.warning("Removed product image could not be deleted from storage.")
                        removal_warning = True
            if removal_warning:
                flash(
                    "The image was removed from the catalog, but its stored file could not be cleaned up.",
                    "warning",
                )
            else:
                flash("The product image was removed.", "success")
            return redirect(url_for("admin_products"))

        if request.form.get("image_action", "save") != "save":
            abort(400, description="Choose a valid product image action.")

        values, error = parse_product_form(request.form)
        if error:
            flash(error, "error")
            return redirect(url_for("admin_products"))

        new_image_key, image_error = store_uploaded_product_image()
        if image_error:
            flash(image_error, "error")
            return redirect(url_for("admin_products"))

        old_image_key = product.image_key
        product.name = values["name"]
        product.slug = make_product_slug(values["name"], product_id=product.id)
        product.skin_type = values["skin_type"]
        product.price = values["price"]
        product.stock = values["stock"]
        product.description = values["description"]
        if new_image_key:
            product.image_key = new_image_key
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            cleanup_uploaded_product_image(storage, new_image_key)
            app.logger.exception("Product update failed.")
            flash("The product could not be updated. Please try again.", "error")
            return redirect(url_for("admin_products"))

        if new_image_key and old_image_key and old_image_key.startswith("products/"):
            try:
                storage.delete(old_image_key)
            except ProductImageStorageError:
                app.logger.warning("Replaced product image could not be deleted from storage.")
                flash(
                    f"{product.name} was updated, but its previous image file could not be cleaned up.",
                    "warning",
                )
                return redirect(url_for("admin_products"))
        flash(f"{product.name} was updated.", "success")
        return redirect(url_for("admin_products"))

    @app.route("/admin/customers")
    @admin_required
    def admin_customers():
        customers = (
            db.session.query(
                Order.user_email.label("email"),
                func.max(Order.customer_name).label("name"),
                func.max(Order.phone_number).label("phone"),
                func.count(Order.id).label("order_count"),
                func.sum(Order.total_amount).label("lifetime_spend"),
                func.max(Order.created_at).label("last_order"),
            )
            .group_by(Order.user_email)
            .order_by(func.max(Order.created_at).desc())
            .all()
        )
        return render_template("admin_customers.html", active_page="customers", customers=customers)

    @app.route("/admin/settings", methods=["GET", "POST"])
    @admin_required
    def admin_settings():
        profile = get_or_create_admin_profile()
        if request.method == "POST":
            display_name = request.form.get("display_name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            bio = request.form.get("bio", "").strip()

            if not display_name or len(display_name) > 150:
                flash("Display name is required and must be 150 characters or fewer.", "error")
            elif email and (len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
                flash("Enter a valid contact email address.", "error")
            elif len(phone) > 40:
                flash("Phone number must be 40 characters or fewer.", "error")
            elif len(bio) > 500:
                flash("Bio must be 500 characters or fewer.", "error")
            else:
                profile.display_name = display_name
                profile.email = email or None
                profile.phone = phone or None
                profile.bio = bio or None
                db.session.commit()
                flash("Your admin profile has been updated.", "success")
                return redirect(url_for("admin_settings"))

        return render_template("admin_settings.html", active_page="settings", profile=profile)

    @app.route("/admin/settings/password", methods=["POST"])
    @admin_required
    def admin_change_password():
        profile = get_admin_profile()
        if profile is None:
            abort(404)

        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not verify_admin_password(profile, current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 12:
            flash("Choose a password with at least 12 characters.", "error")
        elif len(new_password) > 256:
            flash("Password must be 256 characters or fewer.", "error")
        elif new_password != confirm_password:
            flash("New password and confirmation do not match.", "error")
        elif hmac.compare_digest(current_password.encode("utf-8"), new_password.encode("utf-8")):
            flash("Choose a new password that differs from your current password.", "error")
        else:
            profile.password_hash = generate_password_hash(new_password)
            db.session.commit()
            session["admin_credential_version"] = admin_credential_version()
            session["admin_csrf_token"] = secrets.token_urlsafe(32)
            flash("Your login password has been changed.", "success")
            return redirect(url_for("admin_settings"))

        return redirect(url_for("admin_settings"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
