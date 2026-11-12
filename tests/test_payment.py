import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from app.payment import create_transaction


class PaymentAmountTests(unittest.TestCase):
    @patch("app.payment.PAYSTACK_SECRET_KEY", "test-secret")
    @patch("app.payment.requests.post")
    def test_paystack_amount_conversion_uses_decimal_kobo(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {"status": True, "data": {"reference": "test"}}
        post.return_value = response

        result = create_transaction(Decimal("12.34"), "buyer@example.test")

        self.assertEqual(result["reference"], "test")
        self.assertEqual(post.call_args.kwargs["json"]["amount"], 1234)

    @patch("app.payment.PAYSTACK_SECRET_KEY", "test-secret")
    @patch("app.payment.requests.post")
    def test_paystack_rejects_amounts_with_fractional_kobo(self, post):
        result = create_transaction(Decimal("12.345"), "buyer@example.test")

        self.assertIn("two decimal places", result["error"])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
