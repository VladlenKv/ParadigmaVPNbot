"""create bot schema, move bot tables out of public schema

Revision ID: 20260702_0003
Revises: 20260510_0002
Create Date: 2026-07-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0003"
down_revision: str | None = "20260510_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create bot schema
    op.execute("CREATE SCHEMA IF NOT EXISTS bot")

    # ── Create bot.users ──────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(128)),
        sa.Column("first_name", sa.String(256)),
        sa.Column("last_name", sa.String(256)),
        sa.Column("language_code", sa.String(16)),
        sa.Column("referral_code", sa.String(128)),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("telegram_id"),
        schema="bot",
    )
    op.create_index("ix_bot_users_telegram_id", "users", ["telegram_id"], schema="bot")

    # Copy data from public.users if it exists (Integer PK version from earlier Alembic runs)
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "users", schema=None):
        result = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = 'users' AND data_type = 'integer' AND table_schema = 'public')")
        )
        if result.scalar():
            conn.execute(
                sa.text("INSERT INTO bot.users (id, telegram_id, username, first_name, last_name, "
                        "language_code, referral_code, is_blocked, is_admin, created_at, updated_at) "
                        "SELECT id, telegram_id, username, first_name, last_name, "
                        "language_code, referral_code, is_blocked, is_admin, created_at, updated_at "
                        "FROM public.users "
                        "ON CONFLICT DO NOTHING")
            )

    # ── Create bot.plans ──────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("traffic_limit_gb", sa.Integer()),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code"),
        schema="bot",
    )

    # Seed plans
    op.bulk_insert(
        sa.table(
            "plans",
            sa.column("code"),
            sa.column("title"),
            sa.column("description"),
            sa.column("price_amount"),
            sa.column("currency"),
            sa.column("duration_days"),
            sa.column("traffic_limit_gb"),
            sa.column("device_limit"),
            sa.column("sort_order"),
            schema="bot",
        ),
        [
            {"code": "start_30", "title": "Start", "description": "30 days, 100 GB, 1 device",
             "price_amount": 199, "currency": "RUB", "duration_days": 30,
             "traffic_limit_gb": 100, "device_limit": 1, "sort_order": 10},
            {"code": "plus_30", "title": "Plus", "description": "30 days, 300 GB, 3 devices",
             "price_amount": 349, "currency": "RUB", "duration_days": 30,
             "traffic_limit_gb": 300, "device_limit": 3, "sort_order": 20},
            {"code": "premium_30", "title": "Premium", "description": "30 days, unlimited traffic, 5 devices",
             "price_amount": 499, "currency": "RUB", "duration_days": 30,
             "traffic_limit_gb": None, "device_limit": 5, "sort_order": 30},
        ],
    )

    # ── Create bot.subscriptions ──────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot.users.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("bot.plans.id")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("marzban_username", sa.String(128), nullable=False),
        sa.Column("subscription_url", sa.Text()),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("traffic_limit_bytes", sa.BigInteger()),
        sa.Column("last_traffic_used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("additional_devices_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="bot",
    )
    op.create_index("ix_bot_subscriptions_user_id", "subscriptions", ["user_id"], schema="bot")
    op.create_index("ix_bot_subscriptions_expires_at", "subscriptions", ["expires_at"], schema="bot")
    op.create_index("ix_bot_subscriptions_marzban_username", "subscriptions", ["marzban_username"], schema="bot")

    # Copy data from public.subscriptions
    conn = op.get_bind()
    if conn.dialect.has_table(conn, "subscriptions", schema=None):
        result = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = 'subscriptions' AND table_schema = 'public')")
        )
        if result.scalar():
            conn.execute(
                sa.text("INSERT INTO bot.subscriptions (id, user_id, plan_id, status, marzban_username, "
                        "subscription_url, starts_at, expires_at, traffic_limit_bytes, "
                        "last_traffic_used_bytes, additional_devices_count, created_at, updated_at) "
                        "SELECT id, user_id, plan_id, status, marzban_username, "
                        "subscription_url, starts_at, expires_at, traffic_limit_bytes, "
                        "last_traffic_used_bytes, additional_devices_count, created_at, updated_at "
                        "FROM public.subscriptions "
                        "ON CONFLICT DO NOTHING")
            )

    # ── Create bot.payments ───────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot.users.id"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("bot.subscriptions.id")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(128), unique=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="bot",
    )
    op.create_index("ix_bot_payments_user_id", "payments", ["user_id"], schema="bot")
    op.create_index("ix_bot_payments_subscription_id", "payments", ["subscription_id"], schema="bot")

    # Copy data from public.payments
    if conn.dialect.has_table(conn, "payments", schema=None):
        result = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = 'payments' AND table_schema = 'public')")
        )
        if result.scalar():
            conn.execute(
                sa.text("INSERT INTO bot.payments (id, user_id, subscription_id, provider, "
                        "provider_payment_id, amount, currency, status, payload_json, "
                        "created_at, updated_at) "
                        "SELECT id, user_id, subscription_id, provider, "
                        "provider_payment_id, amount, currency, status, payload_json, "
                        "created_at, updated_at "
                        "FROM public.payments "
                        "ON CONFLICT DO NOTHING")
            )

    # ── Create bot.bot_events ─────────────────────────────────────────
    op.create_table(
        "bot_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("bot.users.id")),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="bot",
    )
    op.create_index("ix_bot_bot_events_user_id", "bot_events", ["user_id"], schema="bot")
    op.create_index("ix_bot_bot_events_event_type", "bot_events", ["event_type"], schema="bot")

    # Copy data from public.bot_events
    if conn.dialect.has_table(conn, "bot_events", schema=None):
        result = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = 'bot_events' AND table_schema = 'public')")
        )
        if result.scalar():
            conn.execute(
                sa.text("INSERT INTO bot.bot_events (id, user_id, event_type, payload_json, created_at) "
                        "SELECT id, user_id, event_type, payload_json, created_at "
                        "FROM public.bot_events "
                        "ON CONFLICT DO NOTHING")
            )

    # ── Create bot.settings ───────────────────────────────────────────
    op.create_table(
        "settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="bot",
    )

    # Copy data from public.settings
    if conn.dialect.has_table(conn, "settings", schema=None):
        result = conn.execute(
            sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                     "WHERE table_name = 'settings' AND table_schema = 'public')")
        )
        if result.scalar():
            conn.execute(
                sa.text("INSERT INTO bot.settings (key, value_json, updated_at) "
                        "SELECT key, value_json, updated_at "
                        "FROM public.settings "
                        "ON CONFLICT DO NOTHING")
            )


def downgrade() -> None:
    op.drop_table("settings", schema="bot")
    op.drop_index("ix_bot_bot_events_event_type", table_name="bot_events", schema="bot")
    op.drop_index("ix_bot_bot_events_user_id", table_name="bot_events", schema="bot")
    op.drop_table("bot_events", schema="bot")
    op.drop_index("ix_bot_payments_subscription_id", table_name="payments", schema="bot")
    op.drop_index("ix_bot_payments_user_id", table_name="payments", schema="bot")
    op.drop_table("payments", schema="bot")
    op.drop_index("ix_bot_subscriptions_marzban_username", table_name="subscriptions", schema="bot")
    op.drop_index("ix_bot_subscriptions_expires_at", table_name="subscriptions", schema="bot")
    op.drop_index("ix_bot_subscriptions_user_id", table_name="subscriptions", schema="bot")
    op.drop_table("subscriptions", schema="bot")
    op.drop_table("plans", schema="bot")
    op.drop_index("ix_bot_users_telegram_id", table_name="users", schema="bot")
    op.drop_table("users", schema="bot")
    op.execute("DROP SCHEMA IF EXISTS bot")
