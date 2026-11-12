from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_migrate import Migrate
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from app.config import (
        ADMIN_PASSWORD,
        ADMIN_USERNAME,
        APP_ENV,
        DATABASE_URL,
        DIRECT_DATABASE_URL,
        PAYSTACK_PUBLIC_KEY,
        SECRET_KEY,
        SQLALCHEMY_DATABASE_URI,
    )
    from app.models import AdminProfile, Customer, Order, OrderItem, PaymentAuditLog, Product, db
except ImportError:  # pragma: no cover - compatibility for direct script execution
    from config import (
        ADMIN_PASSWORD,
        ADMIN_USERNAME,
        APP_ENV,
        DATABASE_URL,
        DIRECT_DATABASE_URL,
        PAYSTACK_PUBLIC_KEY,
        SECRET_KEY,
        SQLALCHEMY_DATABASE_URI,
    )
    from models import AdminProfile, Customer, Order, OrderItem, PaymentAuditLog, Product, db


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "payments"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def seed_products():
    if Product.query.first():
        return

    products = [
        {
            "name": "Niacinamide Balancing Serum",
            "slug": "niacinamide-balancing-serum",
            "skin_type": "oily",
            "price": 30.00,
            "description": "Lightweight serum for oily and combination skin.",
            "stock": 25,
        },
        {
            "name": "Gentle Cream Cleanser",
            "slug": "gentle-cream-cleanser",
            "skin_type": "dry",
            "price": 18.00,
            "description": "Comforting cleanser for normal to dry skin.",
            "stock": 30,
        },
        {
            "name": "Vitamin C Glow Essence",
            "slug": "vitamin-c-glow-essence",
            "skin_type": "all",
            "price": 28.00,
            "description": "Brightening treatment to support an even-looking glow.",
            "stock": 20,
        },
        {
            "name": "Hydrating Barrier Cream",
            "slug": "hydrating-barrier-cream",
            "skin_type": "dry",
            "price": 34.00,
            "description": "Deep hydration to reinforce the skin barrier.",
            "stock": 18,
        },
    ]

    for payload in products:
        db.session.add(Product(**payload))

    db.session.commit()


def build_cart_summary(cart):
    items = []
    subtotal = 0.0

    for entry in cart:
        product = Product.query.get(entry.get("product_id"))
        if product is None:
            continue

        quantity = max(1, int(entry.get("quantity", 1)))
        line_total = float(product.price) * quantity
        subtotal += line_total
        items.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": float(product.price),
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    return {"items": items, "subtotal": round(subtotal, 2), "total": round(subtotal, 2)}


def save_receipt_file(file_storage):
    if file_storage is None or not getattr(file_storage, "filename", None):
        return None

    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file_storage.filename}"
    safe_name = os.path.basename(filename)
    saved_path = UPLOAD_DIR / safe_name
    file_storage.save(saved_path)
    return f"/static/uploads/payments/{safe_name}"


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
        price = float(form.get("price", ""))
        stock = int(form.get("stock", ""))
    except (TypeError, ValueError):
        return None, "Enter a valid price and whole-number stock quantity."

    if not math.isfinite(price) or price <= 0:
        return None, "Price must be a positive number."
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
        if request.path in {"/signup", "/signin", "/account"} and not customer_csrf_token:
            customer_csrf_token = secrets.token_urlsafe(32)
            session["customer_csrf_token"] = customer_csrf_token
        admin_profile = get_admin_profile() if session.get("admin_authenticated") is True else None
        return {
            "current_year": datetime.now().year,
            "admin_csrf_token": csrf_token,
            "customer_csrf_token": customer_csrf_token,
            "admin_profile": admin_profile,
        }

    @app.template_filter("naira")
    def format_naira(amount):
        return f"₦{float(amount or 0):,.2f}"

    @app.before_request
    def validate_admin_csrf():
        if request.method == "POST" and request.path.startswith("/admin"):
            expected_token = session.get("admin_csrf_token", "")
            submitted_token = request.form.get("csrf_token", "")
            if not expected_token or not submitted_token or not hmac.compare_digest(
                expected_token, submitted_token
            ):
                abort(400, description="The form expired or its security token is invalid. Reload and try again.")
        elif request.method == "POST" and request.path in {"/signup", "/signin", "/signout"}:
            expected_token = session.get("customer_csrf_token", "")
            submitted_token = request.form.get("csrf_token", "")
            if not expected_token or not submitted_token or not hmac.compare_digest(
                expected_token, submitted_token
            ):
                abort(400, description="The form expired or its security token is invalid. Reload and try again.")

    @app.before_request
    def ensure_seed_data():
        with app.app_context():
            db.create_all()
            seed_products()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/shop")
    def shop():
        return render_template("shop.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

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
        skin_type = request.args.get("type")
        query = Product.query
        if skin_type:
            query = query.filter(Product.skin_type == skin_type)
        return render_template("products.html", products=query.order_by(Product.id).all())

    @app.route("/product/<int:product_id>")
    def product_detail(product_id):
        product = Product.query.get_or_404(product_id)
        return render_template("product_details.html", product=product, PAYSTACK_PUBLIC_KEY=PAYSTACK_PUBLIC_KEY)

    @app.route("/cart")
    def cart():
        return render_template(
            "cart.html",
            cart=session.get("cart", []),
            PAYSTACK_PUBLIC_KEY=PAYSTACK_PUBLIC_KEY,
        )

    @app.route("/cart/add", methods=["POST"])
    def add_to_cart():
        product_id = int(request.form.get("product_id"))
        quantity = int(request.form.get("quantity", 1))
        product = Product.query.get_or_404(product_id)

        cart = session.get("cart", [])
        for item in cart:
            if int(item.get("product_id")) == product_id:
                item["quantity"] = int(item.get("quantity", 1)) + quantity
                session["cart"] = cart
                return redirect("/cart")

        cart.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": float(product.price),
                "quantity": quantity,
            }
        )
        session["cart"] = cart
        return redirect("/cart")

    @app.route("/cart/update", methods=["POST"])
    def update_cart():
        cart = session.get("cart", [])
        for item in cart:
            product_id = int(item.get("product_id"))
            qty = int(request.form.get(f"quantity_{product_id}", item.get("quantity", 1)))
            item["quantity"] = max(1, qty)
        session["cart"] = cart
        return redirect("/cart")

    @app.route("/cart/remove/<int:product_id>")
    def remove_from_cart(product_id):
        cart = session.get("cart", [])
        session["cart"] = [item for item in cart if int(item.get("product_id")) != product_id]
        return redirect("/cart")

    @app.route("/checkout", methods=["GET", "POST"])
    def checkout():
        if request.method == "GET":
            return render_template("checkout.html", cart=session.get("cart", []), PAYSTACK_PUBLIC_KEY=PAYSTACK_PUBLIC_KEY)

        payload = request.get_json(silent=True) or request.form.to_dict()
        raw_cart = payload.get("cart") or session.get("cart", [])
        if isinstance(raw_cart, str):
            try:
                cart = json.loads(raw_cart)
            except (TypeError, ValueError):
                cart = []
        else:
            cart = raw_cart

        if not cart:
            return jsonify({"status": "error", "message": "Your cart is empty."}), 400

        summary = build_cart_summary(cart)
        if not summary["items"]:
            return jsonify({"status": "error", "message": "Cart items could not be validated."}), 400

        customer = get_current_customer()
        if customer is None:
            email = (payload.get("email") or "").strip().lower()
            name = (payload.get("name") or payload.get("customer_name") or "Customer").strip()
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

        if not email:
            return jsonify({"status": "error", "message": "Customer email is required."}), 400

        if payment_method in {"opay", "bank_transfer", "manual_transfer"} and not payment_reference:
            return jsonify({"status": "error", "message": "A payment reference is required for the selected payment method."}), 400

        receipt_file = None
        if request.files and "receipt" in request.files:
            receipt_file = save_receipt_file(request.files["receipt"])
        elif payload.get("receipt_file"):
            receipt_file = payload.get("receipt_file")

        if payment_method in {"opay", "bank_transfer", "manual_transfer"} and not receipt_file:
            return jsonify({"status": "error", "message": "A receipt upload is required for verification."}), 400

        if payment_reference and Order.query.filter_by(payment_reference=payment_reference).first():
            return jsonify({"status": "error", "message": "This payment reference has already been used."}), 409

        order = Order(
            customer_id=customer.id if customer else None,
            customer_name=name,
            user_email=email,
            phone_number=phone,
            total_amount=summary["total"],
            payment_method=payment_method,
            payment_status="awaiting_verification" if payment_method in {"opay", "bank_transfer", "manual_transfer"} else "pending",
            fulfillment_status="pending",
            payment_reference=payment_reference or None,
            receipt_file=receipt_file,
        )
        db.session.add(order)
        db.session.flush()

        for item in summary["items"]:
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_price=item["price"],
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

        session["cart"] = []

        if request.accept_mimetypes.accept_json and not request.files:
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
            db.session.query(func.coalesce(func.sum(Order.total_amount), 0.0))
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
        order = Order.query.get_or_404(order_id)
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

            product = Product(**values, slug=make_product_slug(values["name"]))
            db.session.add(product)
            db.session.commit()
            flash(f"{product.name} was added to the catalog.", "success")
            return redirect(url_for("admin_products"))

        products = Product.query.order_by(Product.name.asc()).all()
        return render_template("admin_products.html", active_page="products", products=products)

    @app.route("/admin/products/<int:product_id>/edit", methods=["POST"])
    @admin_required
    def admin_edit_product(product_id):
        product = Product.query.get_or_404(product_id)
        values, error = parse_product_form(request.form)
        if error:
            flash(error, "error")
            return redirect(url_for("admin_products"))

        product.name = values["name"]
        product.slug = make_product_slug(values["name"], product_id=product.id)
        product.skin_type = values["skin_type"]
        product.price = values["price"]
        product.stock = values["stock"]
        product.description = values["description"]
        db.session.commit()
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
