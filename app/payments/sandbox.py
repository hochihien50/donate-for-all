"""Local test gateway. Still goes through the REAL signed-webhook path; nothing can be completed
without a valid HMAC. Refused at startup when APP_ENV=production. Use scripts/sandbox_pay.py."""
import hashlib
import hmac
import json

from .base import InvalidSignature, PaymentProvider, ProviderOrder, WebhookResult


class SandboxProvider(PaymentProvider):
    name = "sandbox"

    def create_order(self, order_ref, amount, description):
        return ProviderOrder(payment_url=f"sandbox://pay/{order_ref}", raw={"note": "use scripts/sandbox_pay.py"})

    def parse_webhook(self, headers, raw_body):
        secret = self.config["SANDBOX_WEBHOOK_SECRET"]
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get("X-Sandbox-Signature", "")):
            raise InvalidSignature("bad signature")
        try:
            d = json.loads(raw_body)
            return WebhookResult(
                event_id=str(d["event_id"]),
                provider_order_id=str(d["order_id"]),
                provider_transaction_id=str(d["transaction_id"]),
                amount=int(d["amount"]),
                paid=True,
                raw=d,
            )
        except (ValueError, KeyError, TypeError):
            raise InvalidSignature("malformed payload")
