from decimal import Decimal, InvalidOperation

import requests

try:
    from app.config import PAYSTACK_SECRET_KEY
except ImportError:  # pragma: no cover - fallback for direct script execution
    from config import PAYSTACK_SECRET_KEY

PAYSTACK_API_URL = "https://api.paystack.co/"


def build_headers():
    headers = {"Content-Type": "application/json"}
    if PAYSTACK_SECRET_KEY:
        headers["Authorization"] = f"Bearer {PAYSTACK_SECRET_KEY}"
    return headers


def create_transaction(amount, email, *, currency="NGN"):
    """Create a transaction with Paystack for the user."""
    if not PAYSTACK_SECRET_KEY:
        return {"error": "Paystack secret key is not configured."}

    try:
        amount_decimal = Decimal(str(amount))
        amount_kobo = amount_decimal * 100
        if (
            not amount_decimal.is_finite()
            or amount_decimal <= 0
            or amount_kobo != amount_kobo.to_integral_value()
        ):
            return {"error": "Amount must be positive and use no more than two decimal places."}
    except (InvalidOperation, TypeError, ValueError):
        return {"error": "Enter a valid payment amount."}

    payload = {
        "email": email,
        "amount": int(amount_kobo),
        "currency": currency,
    }

    response = requests.post(
        f"{PAYSTACK_API_URL}transaction/initialize",
        headers=build_headers(),
        json=payload,
        timeout=15,
    )

    if response.status_code != 200:
        return {"error": "Failed to connect to Paystack API"}

    data = response.json()
    if data.get("status"):
        return data.get("data", {})
    return {"error": data.get("message", "Unable to initialize transaction")}


def verify_transaction(reference):
    """Verify a transaction after payment has been completed."""
    if not PAYSTACK_SECRET_KEY:
        return {"error": "Paystack secret key is not configured."}

    response = requests.get(
        f"{PAYSTACK_API_URL}transaction/verify/{reference}",
        headers=build_headers(),
        timeout=15,
    )

    if response.status_code != 200:
        return {"error": "Failed to verify transaction"}

    payload = response.json()
    if payload.get("status") and payload.get("data", {}).get("status") == "success":
        return payload.get("data", {})
    return {"error": payload.get("message", "Payment verification failed")}
