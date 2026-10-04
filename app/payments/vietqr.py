import hashlib
import hmac
import json
import re
from urllib.parse import quote

from .base import InvalidSignature, PaymentProvider, ProviderError, ProviderOrder, WebhookResult

REF_RE = re.compile(r"DN[0-9A-F]{12}")


class VietQRProvider(PaymentProvider):
    """Bank-transfer QR (VietQR/NAPAS). Money arrives in your bank account; a bank-notification
    provider (e.g. SePay, Casso) POSTs the transaction to our webhook, signed with HMAC-SHA256
    (hex) in the X-Signature header. Adjust parse_webhook field names to your chosen provider."""

    name = "vietqr"

    def create_order(self, order_ref, amount, description):
        c = self.config
        if not (c["VIETQR_BANK_ID"] and c["VIETQR_ACCOUNT_NO"]):
            raise ProviderError("VietQR bank account is not configured")
        qr = (
            f"https://img.vietqr.io/image/{c['VIETQR_BANK_ID']}-{c['VIETQR_ACCOUNT_NO']}-compact2.png"
            f"?amount={amount}&addInfo={quote(order_ref)}&accountName={quote(c['VIETQR_ACCOUNT_NAME'])}"
        )
        return ProviderOrder(qr_code=qr, raw={"transfer_content": order_ref})

    def parse_webhook(self, headers, raw_body):
        secret = self.config["VIETQR_WEBHOOK_SECRET"]
        sig = headers.get("X-Signature", "")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest() if secret else ""
        if not secret or not hmac.compare_digest(expected, sig):
            raise InvalidSignature("bad signature")
        try:
            d = json.loads(raw_body)
            m = REF_RE.search(str(d["content"]).upper())
            if not m:
                raise InvalidSignature("no order reference in transfer content")
            return WebhookResult(
                event_id=str(d["id"]),
                provider_order_id=m.group(0),
                provider_transaction_id=str(d["id"]),
                amount=int(d["transferAmount"]),
                paid=d.get("transferType", "in") == "in",
                raw=d,
            )
        except (ValueError, KeyError, TypeError):
            raise InvalidSignature("malformed payload")
