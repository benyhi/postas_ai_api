"""billing base

Revision ID: 20260528_0001
Revises:
Create Date: 2026-05-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260528_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="ARS", nullable=False),
        sa.Column("billing_interval", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_billing_plans_code"),
    )
    op.create_index("ix_billing_plans_code", "billing_plans", ["code"], unique=False)

    op.create_table(
        "billing_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_billing_features_key"),
    )
    op.create_index("ix_billing_features_key", "billing_features", ["key"], unique=False)

    op.create_table(
        "billing_plan_features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("reset_period", sa.String(length=20), nullable=True),
        sa.Column("hard_limit", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["billing_features.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "feature_id", name="uq_billing_plan_features_plan_feature"),
    )
    op.create_index("ix_billing_plan_features_feature_id", "billing_plan_features", ["feature_id"], unique=False)
    op.create_index("ix_billing_plan_features_plan_id", "billing_plan_features", ["plan_id"], unique=False)

    op.create_table(
        "billing_tenant_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_tenant_subscriptions_plan_id", "billing_tenant_subscriptions", ["plan_id"], unique=False)
    op.create_index("ix_billing_tenant_subscriptions_tenant_id", "billing_tenant_subscriptions", ["tenant_id"], unique=False)
    op.create_index(
        "uq_billing_tenant_active_subscription",
        "billing_tenant_subscriptions",
        ["tenant_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('trialing', 'active')"),
        postgresql_where=sa.text("status IN ('trialing', 'active')"),
    )

    op.create_table(
        "billing_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=120), nullable=True),
        sa.Column("provider_status", sa.String(length=80), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="ARS", nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_tenant_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_payments_tenant_id", "billing_payments", ["tenant_id"], unique=False)

    op.create_table(
        "billing_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("feature_key", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "feature_key", "idempotency_key", name="uq_billing_usage_events_idempotency"),
    )
    op.create_index("ix_billing_usage_events_feature_key", "billing_usage_events", ["feature_key"], unique=False)
    op.create_index("ix_billing_usage_events_period_key", "billing_usage_events", ["period_key"], unique=False)
    op.create_index("ix_billing_usage_events_tenant_id", "billing_usage_events", ["tenant_id"], unique=False)
    op.create_index(
        "ix_billing_usage_events_tenant_feature_idempotency",
        "billing_usage_events",
        ["tenant_id", "feature_key", "idempotency_key"],
        unique=False,
    )

    op.create_table(
        "billing_usage_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("feature_key", sa.String(length=80), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "feature_key", "period_key", name="uq_billing_usage_counters_period"),
    )
    op.create_index("ix_billing_usage_counters_feature_key", "billing_usage_counters", ["feature_key"], unique=False)
    op.create_index("ix_billing_usage_counters_period_key", "billing_usage_counters", ["period_key"], unique=False)
    op.create_index("ix_billing_usage_counters_tenant_id", "billing_usage_counters", ["tenant_id"], unique=False)
    op.create_index(
        "ix_billing_usage_counters_tenant_feature_period",
        "billing_usage_counters",
        ["tenant_id", "feature_key", "period_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_billing_usage_counters_tenant_feature_period", table_name="billing_usage_counters")
    op.drop_index("ix_billing_usage_counters_tenant_id", table_name="billing_usage_counters")
    op.drop_index("ix_billing_usage_counters_period_key", table_name="billing_usage_counters")
    op.drop_index("ix_billing_usage_counters_feature_key", table_name="billing_usage_counters")
    op.drop_table("billing_usage_counters")

    op.drop_index("ix_billing_usage_events_tenant_feature_idempotency", table_name="billing_usage_events")
    op.drop_index("ix_billing_usage_events_tenant_id", table_name="billing_usage_events")
    op.drop_index("ix_billing_usage_events_period_key", table_name="billing_usage_events")
    op.drop_index("ix_billing_usage_events_feature_key", table_name="billing_usage_events")
    op.drop_table("billing_usage_events")

    op.drop_index("ix_billing_payments_tenant_id", table_name="billing_payments")
    op.drop_table("billing_payments")

    op.drop_index("uq_billing_tenant_active_subscription", table_name="billing_tenant_subscriptions")
    op.drop_index("ix_billing_tenant_subscriptions_tenant_id", table_name="billing_tenant_subscriptions")
    op.drop_index("ix_billing_tenant_subscriptions_plan_id", table_name="billing_tenant_subscriptions")
    op.drop_table("billing_tenant_subscriptions")

    op.drop_index("ix_billing_plan_features_plan_id", table_name="billing_plan_features")
    op.drop_index("ix_billing_plan_features_feature_id", table_name="billing_plan_features")
    op.drop_table("billing_plan_features")

    op.drop_index("ix_billing_features_key", table_name="billing_features")
    op.drop_table("billing_features")

    op.drop_index("ix_billing_plans_code", table_name="billing_plans")
    op.drop_table("billing_plans")
