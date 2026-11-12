from __future__ import annotations

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)
    skin_type = db.Column(db.String(80), nullable=False, default="all")
    price = db.Column(db.Numeric(14, 2), nullable=False)
    description = db.Column(db.Text, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Product {self.name}>"


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=False, unique=True)
    phone_number = db.Column(db.String(40), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = db.relationship("Order", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer {self.email}>"


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    customer_name = db.Column(db.String(150), nullable=False)
    user_email = db.Column(db.String(254), nullable=False)
    phone_number = db.Column(db.String(40), nullable=True)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False)
    inventory_deducted = db.Column(db.Boolean, nullable=False, default=False)
    payment_method = db.Column(db.String(40), nullable=False, default="manual_transfer")
    payment_status = db.Column(db.String(40), nullable=False, default="pending")
    fulfillment_status = db.Column(db.String(40), nullable=False, default="pending")
    payment_reference = db.Column(db.String(120), unique=True, nullable=True)
    receipt_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    customer = db.relationship("Customer", back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order {self.id}>"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<OrderItem order={self.order_id} product={self.product_id}>"


class PaymentAuditLog(db.Model):
    __tablename__ = "payment_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    event = db.Column(db.String(80), nullable=False)
    details = db.Column(db.Text, nullable=True)
    actor = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    order = db.relationship("Order")

    def __repr__(self) -> str:
        return f"<PaymentAuditLog order={self.order_id} event={self.event}>"


class AdminProfile(db.Model):
    __tablename__ = "admin_profiles"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    display_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(254), nullable=True)
    phone = db.Column(db.String(40), nullable=True)
    bio = db.Column(db.String(500), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AdminProfile {self.username}>"

