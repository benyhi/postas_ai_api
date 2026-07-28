"""ARCA multi-tenant profiles and invoices

Revision ID: 20260727_01
Revises: 20260528_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260727_01"
down_revision: str | None = "20260528_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "arca_fiscal_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("arca_cuit", sa.String(11), nullable=False),
        sa.Column("certificate_encrypted", sa.Text(), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("credential_key_id", sa.String(80), nullable=False),
        sa.Column("certificate_fingerprint", sa.String(64), nullable=False),
        sa.Column("certificate_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_of_sale", sa.Integer(), nullable=False),
        sa.Column("automatic_voucher_type", sa.Integer(), nullable=False),
        sa.Column("concept", sa.Integer(), server_default="1", nullable=False),
        sa.Column("default_vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("default_vat_id", sa.Integer(), server_default="5", nullable=False),
        sa.Column("validation_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credentials_rotated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "environment", name="uq_arca_profile_tenant_environment"),
    )
    op.create_index("ix_arca_profiles_tenant_id", "arca_fiscal_profiles", ["tenant_id"])

    op.create_table(
        "arca_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("fiscal_profile_id", sa.Integer(), sa.ForeignKey("arca_fiscal_profiles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sale_id", sa.String(36), nullable=True),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("arca_cuit", sa.String(11), nullable=False),
        sa.Column("point_of_sale", sa.Integer(), nullable=False),
        sa.Column("voucher_type", sa.Integer(), nullable=False),
        sa.Column("voucher_number", sa.BigInteger(), nullable=True),
        sa.Column("explicit_number", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("concept", sa.Integer(), nullable=False),
        sa.Column("doc_type", sa.Integer(), nullable=False),
        sa.Column("doc_number", sa.String(20), nullable=False),
        sa.Column("receiver_iva_condition_id", sa.Integer(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("service_start_date", sa.Date(), nullable=True),
        sa.Column("service_end_date", sa.Date(), nullable=True),
        sa.Column("payment_due_date", sa.Date(), nullable=True),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("exempt_amount", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("iva_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(40), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("cae", sa.String(32), nullable=True),
        sa.Column("cae_expiration_date", sa.Date(), nullable=True),
        sa.Column("arca_result", sa.String(20), nullable=True),
        sa.Column("arca_response", sa.JSON(), nullable=True),
        sa.Column("observations", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "external_id", name="uq_arca_invoice_tenant_external"),
        sa.UniqueConstraint("tenant_id", "sale_id", name="uq_arca_invoice_tenant_sale"),
        sa.UniqueConstraint("environment", "arca_cuit", "point_of_sale", "voucher_type", "voucher_number", name="uq_arca_invoice_fiscal_reference"),
    )
    op.create_index("ix_arca_invoices_tenant_id", "arca_invoices", ["tenant_id"])
    op.create_index("ix_arca_invoices_fiscal_profile_id", "arca_invoices", ["fiscal_profile_id"])
    op.create_index("ix_arca_invoices_arca_cuit", "arca_invoices", ["arca_cuit"])
    op.create_index("ix_arca_invoices_status", "arca_invoices", ["status"])
    op.create_index("ix_arca_invoices_cae", "arca_invoices", ["cae"])
    op.create_index("ix_arca_invoices_tenant_sale", "arca_invoices", ["tenant_id", "sale_id"])
    op.create_index("ix_arca_invoices_retry", "arca_invoices", ["status", "next_retry_at"])

    op.create_table(
        "arca_invoice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("arca_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("final_unit_price", sa.Numeric(15, 2), nullable=False),
        sa.Column("final_subtotal", sa.Numeric(15, 2), nullable=False),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("vat_id", sa.Integer(), nullable=False),
        sa.Column("vat_amount", sa.Numeric(15, 2), nullable=False),
    )
    op.create_index("ix_arca_invoice_items_invoice_id", "arca_invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("arca_invoice_items")
    op.drop_table("arca_invoices")
    op.drop_table("arca_fiscal_profiles")
