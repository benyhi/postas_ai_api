from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.arca.schemas import (
    AutomaticInvoiceRequest,
    ExplicitInvoiceCreateRequest,
    FiscalProfileResponse,
    FiscalProfileWrite,
    InvoiceCreateRequest,
    InvoiceListResponse,
    InvoiceResponse,
    LastVoucherResponse,
    ProfileValidationResponse,
    RotationResponse,
    SalesPointDiscoveryRequest,
    SalesPointListResponse,
)
from app.arca.crypto import CredentialConfigurationError
from app.arca.service import ArcaDomainError, FiscalProfileService, InvoiceService
from app.billing.dependencies import InternalRequestContext, verify_internal_request
from app.db.session import get_db


router = APIRouter(prefix="/arca/tenants/{tenant_id}", tags=["arca-internal"])


def _authorized_context(context: InternalRequestContext = Depends(verify_internal_request)) -> InternalRequestContext:
    if context.source != "postas_api":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ARCA solo acepta llamadas de postas_api")
    return context


def _raise_domain(exc: ArcaDomainError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


@router.get("/profiles/{environment}", response_model=FiscalProfileResponse)
def get_profile(
    tenant_id: UUID,
    environment: str,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return FiscalProfileService(db).require(tenant_id, environment)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.put("/profiles/{environment}", response_model=FiscalProfileResponse)
def put_profile(
    tenant_id: UUID,
    environment: str,
    payload: FiscalProfileWrite,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    if environment not in {"development", "production"}:
        raise HTTPException(status_code=422, detail="Ambiente ARCA invalido")
    try:
        return FiscalProfileService(db).upsert(tenant_id, environment, payload)
    except ArcaDomainError as exc:
        _raise_domain(exc)
    except CredentialConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "credential_keyring_unavailable", "message": str(exc)},
        ) from exc


@router.delete("/profiles/{environment}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    tenant_id: UUID,
    environment: str,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        FiscalProfileService(db).delete(tenant_id, environment)
    except ArcaDomainError as exc:
        _raise_domain(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/profiles/{environment}/validate", response_model=ProfileValidationResponse)
def validate_profile(
    tenant_id: UUID,
    environment: str,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return FiscalProfileService(db).validate(tenant_id, environment)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.post("/profiles/rotate-keyring", response_model=RotationResponse)
def rotate_keyring(
    tenant_id: UUID,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        service = FiscalProfileService(db)
        service.require_entitlement(tenant_id)
        profiles = [
            profile
            for environment in ("development", "production")
            if (profile := service.get(tenant_id, environment)) is not None
        ]
        rotated = 0
        for profile in profiles:
            if profile.credential_key_id == service.cipher.active_key_id:
                continue
            credentials = service.decrypt(profile)
            profile.certificate_encrypted = service.cipher.encrypt(credentials.certificate)
            profile.private_key_encrypted = service.cipher.encrypt(credentials.private_key)
            profile.access_token_encrypted = service.cipher.encrypt(credentials.access_token)
            profile.credential_key_id = service.cipher.active_key_id
            profile.credentials_rotated_at = datetime.now(timezone.utc)
            rotated += 1
        db.commit()
        return RotationResponse(rotated_profiles=rotated)
    except ArcaDomainError as exc:
        _raise_domain(exc)
    except CredentialConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "credential_keyring_unavailable", "message": str(exc)},
        ) from exc


@router.post("/sales-points", response_model=SalesPointListResponse)
def discover_sales_points(
    tenant_id: UUID,
    payload: SalesPointDiscoveryRequest,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return FiscalProfileService(db).discover_sales_points(tenant_id, payload)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(
    tenant_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).list_invoices(tenant_id, offset=offset, limit=limit)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.post("/invoices/{environment}", response_model=InvoiceResponse, status_code=status.HTTP_202_ACCEPTED)
def create_next_invoice(
    tenant_id: UUID,
    environment: str,
    payload: InvoiceCreateRequest,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).enqueue(tenant_id, environment, payload)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.post("/invoices/{environment}/automatic", response_model=InvoiceResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_automatic_invoice(
    tenant_id: UUID,
    environment: str,
    payload: AutomaticInvoiceRequest,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).enqueue(tenant_id, environment, payload, automatic=True)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.post("/invoices/{environment}/explicit", response_model=InvoiceResponse, status_code=status.HTTP_202_ACCEPTED)
def create_explicit_invoice(
    tenant_id: UUID,
    environment: str,
    payload: ExplicitInvoiceCreateRequest,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    invoice_payload = InvoiceCreateRequest.model_validate(payload.model_dump(exclude={"voucher_number"}))
    try:
        return InvoiceService(db).enqueue(
            tenant_id, environment, invoice_payload, voucher_number=payload.voucher_number
        )
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.get("/invoices/by-external-id/{external_id}", response_model=InvoiceResponse)
def invoice_by_external_id(
    tenant_id: UUID,
    external_id: str,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).get_by_external_id(tenant_id, external_id)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.get("/invoices/by-sale/{sale_id}", response_model=InvoiceResponse)
def invoice_by_sale(
    tenant_id: UUID,
    sale_id: UUID,
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).get_by_sale_id(tenant_id, sale_id)
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.get("/invoices/fiscal", response_model=InvoiceResponse)
def invoice_by_fiscal_reference(
    tenant_id: UUID,
    environment: str = Query(pattern="^(development|production)$"),
    point_of_sale: int = Query(gt=0),
    voucher_type: int = Query(gt=0),
    voucher_number: int = Query(gt=0),
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).get_by_fiscal_reference(
            tenant_id, environment, point_of_sale, voucher_type, voucher_number
        )
    except ArcaDomainError as exc:
        _raise_domain(exc)


@router.get("/last-voucher/{environment}", response_model=LastVoucherResponse)
def last_voucher(
    tenant_id: UUID,
    environment: str,
    voucher_type: int | None = Query(default=None, gt=0),
    _: InternalRequestContext = Depends(_authorized_context),
    db: Session = Depends(get_db),
):
    try:
        return InvoiceService(db).get_last_voucher(tenant_id, environment, voucher_type)
    except ArcaDomainError as exc:
        _raise_domain(exc)
