"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def TS():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False), TS())
    op.create_table("projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), TS())
    op.create_index("ix_projects_user_id", "projects", ["user_id"])
    op.create_table("api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True), TS(),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_api_keys_project_id", "api_keys", ["project_id"])
    op.create_table("donations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("donor_name", sa.String(120)),
        sa.Column("message", sa.String(500)),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), TS(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("amount > 0", name="ck_donations_amount_positive"))
    op.create_index("ix_donations_project_id", "donations", ["project_id"])
    op.create_index("ix_donations_status", "donations", ["status"])
    op.create_table("payment_orders",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("donation_id", sa.Uuid, sa.ForeignKey("donations.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_order_id", sa.String(64), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payment_url", sa.Text), sa.Column("qr_code", sa.Text), sa.Column("deeplink", sa.Text),
        sa.Column("raw_response", sa.JSON), TS(),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider", "provider_order_id", name="uq_payment_orders_provider_order"))
    op.create_index("ix_payment_orders_donation_id", "payment_orders", ["donation_id"])
    op.create_table("transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payment_order_id", sa.Uuid, sa.ForeignKey("payment_orders.id"), nullable=False),
        sa.Column("donation_id", sa.Uuid, sa.ForeignKey("donations.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_transaction_id", sa.String(128), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False), TS(),
        sa.UniqueConstraint("provider", "provider_transaction_id", name="uq_transactions_provider_tx"),
        sa.UniqueConstraint("payment_order_id", name="uq_transactions_one_per_order"))
    op.create_index("ix_transactions_payment_order_id", "transactions", ["payment_order_id"])
    op.create_index("ix_transactions_donation_id", "transactions", ["donation_id"])
    op.create_table("webhook_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("payment_order_id", sa.Uuid, sa.ForeignKey("payment_orders.id")),
        sa.Column("payload", sa.JSON),
        sa.Column("processed", sa.Boolean, nullable=False),
        sa.Column("error", sa.String(255)), TS(),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_events_provider_event"))


def downgrade():
    # Intentionally destructive and manual-only. Never run against production without a backup.
    for t in ("webhook_events", "transactions", "payment_orders", "donations", "api_keys", "projects", "users"):
        op.drop_table(t)
