import uuid
from datetime import datetime, timezone

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def _ts():
    return db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class DonationStatus:
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class OrderStatus:
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = _ts()


class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    created_at = _ts()


class ApiKey(db.Model):
    __tablename__ = "api_keys"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    key_prefix = db.Column(db.String(16), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False, unique=True)  # sha256; plaintext never stored
    created_at = _ts()
    revoked_at = db.Column(db.DateTime(timezone=True))
    project = db.relationship("Project")


class Donation(db.Model):
    __tablename__ = "donations"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    donor_name = db.Column(db.String(120))
    message = db.Column(db.String(500))
    amount = db.Column(db.BigInteger, nullable=False)  # VND, integer
    currency = db.Column(db.String(3), nullable=False, default="VND")
    status = db.Column(db.String(16), nullable=False, default=DonationStatus.PENDING, index=True)
    created_at = _ts()
    completed_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (db.CheckConstraint("amount > 0", name="ck_donations_amount_positive"),)


class PaymentOrder(db.Model):
    __tablename__ = "payment_orders"
    id = db.Column(db.Uuid, primary_key=True, default=uuid.uuid4)
    donation_id = db.Column(db.Uuid, db.ForeignKey("donations.id"), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_order_id = db.Column(db.String(64), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    status = db.Column(db.String(16), nullable=False, default=OrderStatus.PENDING)
    payment_url = db.Column(db.Text)
    qr_code = db.Column(db.Text)
    deeplink = db.Column(db.Text)
    raw_response = db.Column(db.JSON)
    created_at = _ts()
    paid_at = db.Column(db.DateTime(timezone=True))
    donation = db.relationship("Donation", backref="payment_orders")
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_order_id", name="uq_payment_orders_provider_order"),
    )


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    payment_order_id = db.Column(db.Uuid, db.ForeignKey("payment_orders.id"), nullable=False, index=True)
    donation_id = db.Column(db.Uuid, db.ForeignKey("donations.id"), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    provider_transaction_id = db.Column(db.String(128), nullable=False)
    amount = db.Column(db.BigInteger, nullable=False)
    created_at = _ts()
    __table_args__ = (
        db.UniqueConstraint("provider", "provider_transaction_id", name="uq_transactions_provider_tx"),
        db.UniqueConstraint("payment_order_id", name="uq_transactions_one_per_order"),
    )


class WebhookEvent(db.Model):
    __tablename__ = "webhook_events"
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(32), nullable=False)
    event_id = db.Column(db.String(128), nullable=False)
    payment_order_id = db.Column(db.Uuid, db.ForeignKey("payment_orders.id"))
    payload = db.Column(db.JSON)
    processed = db.Column(db.Boolean, nullable=False, default=False)
    error = db.Column(db.String(255))
    created_at = _ts()
    __table_args__ = (
        db.UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"),
    )
