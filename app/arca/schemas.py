from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ArcaEnvironment = Literal["development", "production"]


class FiscalProfileWrite(BaseModel):
    arca_cuit: str = Field(pattern=r"^\d{11}$")
    certificate: str = Field(min_length=1)
    private_key: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    point_of_sale: int = Field(gt=0)
    automatic_voucher_type: int = Field(gt=0)
    concept: int = Field(default=1, ge=1, le=3)
    default_vat_rate: Decimal = Field(default=Decimal("21.00"), ge=0, le=100)
    default_vat_id: int = Field(default=5, gt=0)


class SalesPointDiscoveryRequest(BaseModel):
    arca_environment: ArcaEnvironment
    arca_cuit: str = Field(pattern=r"^\d{11}$")
    certificate: str = Field(min_length=1)
    private_key: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class SalesPointResponse(BaseModel):
    number: int
    emission_type: str
    blocked: bool
    deactivation_date: date | None


class SalesPointListResponse(BaseModel):
    results: list[SalesPointResponse]


class FiscalProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: UUID
    environment: ArcaEnvironment
    arca_cuit: str
    certificate_fingerprint: str
    certificate_expires_at: datetime
    credential_key_id: str
    point_of_sale: int
    automatic_voucher_type: int
    concept: int
    default_vat_rate: Decimal
    default_vat_id: int
    validation_status: str
    validation_error: str | None
    validated_at: datetime | None
    credentials_rotated_at: datetime
    created_at: datetime
    updated_at: datetime


class ReceiverData(BaseModel):
    doc_type: int = Field(default=99, ge=0)
    doc_number: str = Field(default="0", pattern=r"^\d+$", max_length=20)
    iva_condition_id: int = Field(default=5, gt=0)


class InvoiceItemInput(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    final_unit_price: Decimal = Field(ge=0, max_digits=15, decimal_places=2)


class InvoiceCreateRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=160)
    sale_id: UUID | None = None
    actor_id: UUID | None = None
    actor_role: str | None = Field(default=None, max_length=20)
    receiver: ReceiverData = Field(default_factory=ReceiverData)
    invoice_date: date = Field(default_factory=date.today)
    service_start_date: date | None = None
    service_end_date: date | None = None
    payment_due_date: date | None = None
    items: list[InvoiceItemInput] = Field(min_length=1)

    @field_validator("external_id")
    @classmethod
    def strip_external_id(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_dates(self):
        supplied = (self.service_start_date, self.service_end_date, self.payment_due_date)
        if any(supplied) and not all(supplied):
            raise ValueError("Las fechas de servicio y vencimiento deben informarse juntas.")
        if self.service_start_date and self.service_end_date and self.service_start_date > self.service_end_date:
            raise ValueError("La fecha inicial del servicio no puede superar la final.")
        return self


class ExplicitInvoiceCreateRequest(InvoiceCreateRequest):
    voucher_number: int = Field(gt=0)


class AutomaticInvoiceRequest(InvoiceCreateRequest):
    pass


class InvoiceError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class InvoiceResponse(BaseModel):
    id: int
    tenant_id: UUID
    environment: ArcaEnvironment
    fiscal_profile_id: int
    sale_id: UUID | None
    external_id: str
    actor_id: UUID | None
    actor_role: str | None
    status: str
    point_of_sale: int
    voucher_type: int
    voucher_number: int | None
    net_amount: Decimal
    iva_amount: Decimal
    total_amount: Decimal
    cae: str | None
    cae_expiration_date: date | None
    observations: list[str]
    attempt_count: int
    next_retry_at: datetime | None
    error: InvoiceError | None
    created_at: datetime
    updated_at: datetime


class InvoiceListResponse(BaseModel):
    count: int
    results: list[InvoiceResponse]


class LastVoucherResponse(BaseModel):
    environment: ArcaEnvironment
    point_of_sale: int
    voucher_type: int
    last_voucher_number: int


class FiscalReferenceQuery(BaseModel):
    environment: ArcaEnvironment
    point_of_sale: int = Field(gt=0)
    voucher_type: int = Field(gt=0)
    voucher_number: int = Field(gt=0)


class ProfileValidationResponse(BaseModel):
    valid: bool
    status: str
    error: str | None = None


class RotationResponse(BaseModel):
    rotated_profiles: int


class ArcaRawResponse(BaseModel):
    data: dict[str, Any]
