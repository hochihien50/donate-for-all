import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

from .base import InvalidSignature, PaymentProvider, ProviderError, ProviderOrder, WebhookResult

SANDBOX_URL = "https://sb-openapi.zalopay.vn/v2/create"
LIVE_URL = "https://openapi.zalopay.vn/v2/create"


def _mac(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


class ZaloPayProvider(PaymentProvider):
    name = "zalopay"

    def new_order_ref(self) -> str:
        vn = datetime.now(timezone(timedelta(hours=7)))
        return f"{vn:%y%m%d}_{uuid.uuid4().hex[:16]}"  # ZaloPay requires yymmdd_xxx

    def _endpoint(self):
        c = self.config
        return c["ZALOPAY_ENDPOINT"] or (LIVE_URL if c["PAYMENT_MODE"] == "live" else SANDBOX_URL)

    def create_order(self, order_ref, amount, description):
        c = self.config
        if not (c["ZALOPAY_APP_ID"] and c["ZALOPAY_KEY1"]):
            raise ProviderError("ZaloPay credentials are not configured")
        data = {
            "app_id": int(c["ZALOPAY_APP_ID"]),
            "app_user": "donor",
            "app_trans_id": order_ref,
            "app_time": int(time.time() * 1000),
            "amount": amount,
            "item": "[]",
            "embed_data": "{}",
            "description": description,
            "bank_code": "zalopayapp",
            "callback_url": c["ZALOPAY_CALLBACK_URL"],
        }
        keys = ("app_id", "app_trans_id", "app_user", "amount", "app_time", "embed_data", "item")
        data["mac"] = _mac(c["ZALOPAY_KEY1"], "|".join(str(data[k]) for k in keys))
        try:
            resp = requests.post(self._endpoint(), data=data, timeout=15)
            body = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise ProviderError(f"ZaloPay unreachable: {e}")
        if body.get("return_code") != 1:
            raise ProviderError(f"ZaloPay error {body.get('return_code')}: {body.get('return_message')}")
        return ProviderOrder(payment_url=body.get("order_url"), qr_code=body.get("qr_code"), raw=body)

    def parse_webhook(self, headers, raw_body):
        key2 = self.config["ZALOPAY_KEY2"]
        try:
            outer = json.loads(raw_body)
            data_str, mac = outer["data"], outer["mac"]
        except (ValueError, KeyError, TypeError):
            raise InvalidSignature("malformed body")
        if not key2 or not hmac.compare_digest(_mac(key2, data_str), str(mac)):
            raise InvalidSignature("bad mac")
        try:
            d = json.loads(data_str)
            if str(d["app_id"]) != str(self.config["ZALOPAY_APP_ID"]):
                raise InvalidSignature("app_id mismatch")
            return WebhookResult(
                event_id=str(d["zp_trans_id"]),
                provider_order_id=str(d["app_trans_id"]),
                provider_transaction_id=str(d["zp_trans_id"]),
                amount=int(d["amount"]),
                paid=True,  # ZaloPay only calls back for successful payments
                raw=d,
            )
        except (ValueError, KeyError, TypeError):
            raise InvalidSignature("malformed data")

    def webhook_ack(self, outcome):
        return {"return_code": 2 if outcome == "duplicate" else 1, "return_message": outcome}

    def webhook_reject(self):
        return {"return_code": -1, "return_message": "mac not equal"}
