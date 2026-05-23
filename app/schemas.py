import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


DocumentExtractionStatus = Literal[
    "pending",
    "uploading",
    "processing",
    "calling_ai",
    "completed",
    "needs_review",
    "failed",
    "confirmed",
    "cancelled",
]


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return value

    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = re.sub(r"[^\d,.\-]", "", cleaned)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    if cleaned in {"", "-", ".", "-."}:
        return None
    return float(cleaned)


def parse_confidence(value: Any) -> float | None:
    parsed = parse_number(value)
    if parsed is None:
        return None
    if parsed > 1:
        parsed = parsed / 100
    return max(0.0, min(1.0, parsed))


class InvoiceProduct(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str | None = None
    description: str | None = None
    quantity: float | None = None
    price: float | None = None
    total: float | None = None

    @field_validator("quantity", "price", "total", mode="before")
    @classmethod
    def normalize_numeric_fields(cls, value: Any) -> float | None:
        return parse_number(value)


class InvoiceData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_invoice: bool = True
    products: list[InvoiceProduct] = Field(default_factory=list)
    date: str | None = None
    total: float | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def accept_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "confidence" not in normalized:
            normalized["confidence"] = normalized.get("confidence_score") or normalized.get("score") or 0
        if "date" not in normalized:
            normalized["date"] = normalized.get("invoice_date") or normalized.get("fecha")
        if "total" not in normalized:
            normalized["total"] = normalized.get("invoice_total") or normalized.get("importe_total")
        if normalized.get("products") is None:
            normalized["products"] = []
        return normalized

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> float:
        parsed = parse_confidence(value)
        return 0.0 if parsed is None else parsed

    @field_validator("total", mode="before")
    @classmethod
    def normalize_total(cls, value: Any) -> float | None:
        return parse_number(value)


class DocumentExtractionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    uuid: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=80)
    file_url: str = Field(min_length=1, max_length=1000)
    status: DocumentExtractionStatus = "pending"
    raw_response: Any = None
    extracted_data: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts: int = Field(default=0, ge=0)
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    confirmed_at: datetime | None = None

    provider: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_request_id: str | None = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("source_request_id", "document_extraction_id"),
    )

    @model_validator(mode="before")
    @classmethod
    def accept_backend_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "uuid" not in normalized:
            uuid_alias = (
                normalized.get("document_extraction_uuid")
                or normalized.get("document_extraction_id")
                or normalized.get("extraction_uuid")
            )
            if uuid_alias is not None:
                normalized["uuid"] = uuid_alias

        if "tenant_id" not in normalized:
            tenant = normalized.get("tenant") or normalized.get("tenant_uuid") or normalized.get("tenantId")
            if isinstance(tenant, dict):
                tenant = tenant.get("uuid") or tenant.get("id") or tenant.get("tenant_id")
            if tenant is not None:
                normalized["tenant_id"] = str(tenant)

        if "file_url" not in normalized:
            file_url_alias = (
                normalized.get("image_url")
                or normalized.get("signed_image_url")
                or normalized.get("url")
            )
            if file_url_alias is not None:
                normalized["file_url"] = file_url_alias

        return normalized

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> float | None:
        return parse_confidence(value)


class DocumentUsageRecord(BaseModel):
    tenant_id: str
    document_extraction_uuid: UUID
    source: str
    feature: str = "document_extraction"
    provider: str | None = None
    model: str | None = None
    status: DocumentExtractionStatus
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    confidence: float | None = None
    latency_ms: int | None = None
    attempts: int
    error_message: str | None = None
    created_at: datetime
    extra: dict[str, Any] = Field(default_factory=dict)


class DocumentExtractionResponse(BaseModel):
    uuid: UUID
    tenant_id: str
    file_url: str
    status: DocumentExtractionStatus
    raw_response: Any = None
    extracted_data: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts: int
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime
    processing_started_at: datetime
    completed_at: datetime | None = None
    confirmed_at: datetime | None = None
    usage: DocumentUsageRecord
