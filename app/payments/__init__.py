from .base import InvalidSignature, PaymentProvider, ProviderError  # noqa: F401
from .sandbox import SandboxProvider
from .vietqr import VietQRProvider
from .zalopay import ZaloPayProvider

# Add a new provider: subclass PaymentProvider, then register it here. Nothing else changes.
REGISTRY = {p.name: p for p in (ZaloPayProvider, VietQRProvider, SandboxProvider)}


class ProviderNotEnabled(Exception):
    pass


def get_provider(name: str, config) -> PaymentProvider:
    if name not in REGISTRY or name not in config["ENABLED_PROVIDERS"]:
        raise ProviderNotEnabled(name)
    if name == "sandbox" and config["APP_ENV"] == "production":
        raise ProviderNotEnabled(name)
    return REGISTRY[name](config)
