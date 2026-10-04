import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import Donation, DonationStatus, OrderStatus, PaymentOrder, Transaction, WebhookEvent, utcnow
from .payments import ProviderError

log = logging.getLogger(__name__)


def create_donation(provider, project_id, amount, donor_name, message):
    """1) donation=pending 2) payment order 3) call provider 4) return payment info.
    The donation can only ever leave 'pending' via process_webhook()."""
    donation = Donation(project_id=project_id, amount=amount, donor_name=donor_name, message=message)
    ref = provider.new_order_ref()
    order = PaymentOrder(donation=donation, provider=provider.name, provider_order_id=ref, amount=amount)
    db.session.add_all([donation, order])
    db.session.commit()  # persisted before calling the provider, so nothing is lost on failure
    try:
        po = provider.create_order(ref, amount, f"Donate {ref}")
    except ProviderError:
        order.status = OrderStatus.FAILED
        donation.status = DonationStatus.FAILED
        db.session.commit()
        raise
    order.payment_url, order.qr_code, order.deeplink, order.raw_response = (
        po.payment_url, po.qr_code, po.deeplink, po.raw,
    )
    db.session.commit()
    return donation, order


def process_webhook(provider_name, r):
    """Idempotent + atomic. Caller has already verified the signature. Returns an outcome string."""
    event = WebhookEvent(provider=provider_name, event_id=r.event_id, payload=r.raw)
    db.session.add(event)
    try:
        db.session.flush()  # unique(provider, event_id): a replay fails here
    except IntegrityError:
        db.session.rollback()
        return "duplicate"

    order = db.session.execute(
        select(PaymentOrder)
        .where(PaymentOrder.provider == provider_name, PaymentOrder.provider_order_id == r.provider_order_id)
        .with_for_update()  # serialize concurrent webhooks for the same order
    ).scalar_one_or_none()

    if order is None:
        event.error = "unknown order"
        db.session.commit()
        return "ignored"
    event.payment_order_id = order.id

    if order.status == OrderStatus.PAID:
        event.processed = True
        db.session.commit()
        return "duplicate"
    if not r.paid:
        event.error = "not a successful payment"
        db.session.commit()
        return "ignored"
    if r.amount != order.amount:
        event.error = f"amount mismatch: expected {order.amount}, got {r.amount}"
        db.session.commit()
        log.warning("webhook amount mismatch for order %s", order.id)
        return "rejected"

    now = utcnow()
    db.session.add(Transaction(
        payment_order_id=order.id, donation_id=order.donation_id, provider=provider_name,
        provider_transaction_id=r.provider_transaction_id, amount=r.amount,
    ))
    order.status, order.paid_at = OrderStatus.PAID, now
    order.donation.status, order.donation.completed_at = DonationStatus.COMPLETED, now
    event.processed = True
    try:
        db.session.commit()  # event + transaction + order + donation: one atomic commit
    except IntegrityError:
        db.session.rollback()
        log.warning("duplicate provider transaction id %s", r.provider_transaction_id)
        return "duplicate"
    return "completed"
