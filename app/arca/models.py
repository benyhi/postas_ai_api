from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ArcaFiscalProfile(Base):
    __tablename__ = "arca_fiscal_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "environment", name="uq_arca_profile_tenant_environment"),
        Index("ix_arca_profiles_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    arca_cuit: Mapped[str] = mapped_column(String(11), nullable=False)

    certificate_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    credential_key_id: Mapped[str] = mapped_column(String(80), nullable=False)

    certificate_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    certificate_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    point_of_sale: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_voucher_type: Mapped[int] = mapped_column(Integer, nullable=False)
    concept: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    default_vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    default_vat_id: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)

    validation_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credentials_rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invoices: Mapped[list[ArcaInvoice]] = relationship(back_populates="fiscal_profile")


class ArcaInvoice(Base):
    __tablename__ = "arca_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id", name="uq_arca_invoice_tenant_external"),
        UniqueConstraint("tenant_id", "sale_id", name="uq_arca_invoice_tenant_sale"),
        UniqueConstraint(
            "environment",
            "arca_cuit",
            "point_of_sale",
            "voucher_type",
            "voucher_number",
            name="uq_arca_invoice_fiscal_reference",
        ),
        Index("ix_arca_invoices_tenant_sale", "tenant_id", "sale_id"),
        Index("ix_arca_invoices_retry", "status", "next_retry_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_profile_id: Mapped[int] = mapped_column(
        ForeignKey("arca_fiscal_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sale_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    arca_cuit: Mapped[str] = mapped_column(String(11), nullable=False, index=True)
    point_of_sale: Mapped[int] = mapped_column(Integer, nullable=False)
    voucher_type: Mapped[int] = mapped_column(Integer, nullable=False)
    voucher_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    explicit_number: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"), nullable=False)
    concept: Mapped[int] = mapped_column(Integer, nullable=False)

    doc_type: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_number: Mapped[str] = mapped_column(String(20), nullable=False)
    receiver_iva_condition_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    exempt_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0, server_default="0", nullable=False)
    iva_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    status: Mapped[str] = mapped_column(String(40), default="pending", server_default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    cae: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    cae_expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    arca_result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    arca_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    observations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    fiscal_profile: Mapped[ArcaFiscalProfile] = relationship(back_populates="invoices")
    items: Mapped[list[ArcaInvoiceItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class ArcaInvoiceItem(Base):
    __tablename__ = "arca_invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("arca_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    final_unit_price: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    final_subtotal: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    vat_id: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)

    invoice: Mapped[ArcaInvoice] = relationship(back_populates="items")
