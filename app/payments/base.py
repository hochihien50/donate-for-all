import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class ProviderError(Exception):
    """Provider rejected / failed the request."""


class InvalidSignature(Exception):
    """Webhook signature or payload could not be verified."""


@dataclass
class ProviderOrder:
    payment_url: Optional[str] = None
    qr_code: Optional[str] = None
    deeplink: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class WebhookResult:
    event_id: str
    provider_order_id: str
    provider_transaction_id: str
    amount: int
    paid: bool
    raw: dict


class PaymentProvider(ABC):
    name: str

    def __init__(self, config):
        self.config = config

    def new_order_ref(self) -> str:
        return "DN" + uuid.uuid4().hex[:12].upper()

    @abstractmethod
    def create_order(self, order_ref: str, amount: int, description: str) -> ProviderOrder: ...

    @abstractmethod
    def parse_webhook(self, headers, raw_body: bytes) -> WebhookResult:
        """Verify signature and return normalized data. Raise InvalidSignature on any failure."""

    def webhook_ack(self, outcome: str) -> dict:
        return {"status": "ok", "outcome": outcome}

    def webhook_reject(self) -> dict:
        return {"status": "error", "error": "invalid signature"}
