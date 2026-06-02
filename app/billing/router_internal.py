from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.billing.dependencies import InternalRequestContext, get_billing_service, verify_internal_request
from app.billing.schemas import (
    CheckAndConsumeRequest,
    CheckAndConsumeResponse,
    EntitlementCheckRequest,
    EntitlementCheckResponse,
    TenantStatusResponse,
    UsageConsumeRequest,
    UsageConsumeResponse,
)
from app.billing.service import BillingService


router = APIRouter(
    tags=["billing-internal"],
    dependencies=[Depends(verify_internal_request)],
)


@router.get("/tenants/{tenant_id}/status", response_model=TenantStatusResponse)
def get_tenant_status(
    tenant_id: UUID,
    service: BillingService = Depends(get_billing_service),
) -> TenantStatusResponse:
    tenant_status = service.get_tenant_status(tenant_id)
    if tenant_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subscription_not_found",
        )
    return tenant_status


@router.post("/entitlements/check", response_model=EntitlementCheckResponse)
def check_entitlement(
    payload: EntitlementCheckRequest,
    service: BillingService = Depends(get_billing_service),
) -> EntitlementCheckResponse:
    return service.check_entitlement(payload)


@router.post("/usage/consume", response_model=UsageConsumeResponse)
def consume_usage(
    payload: UsageConsumeRequest,
    context: InternalRequestContext = Depends(verify_internal_request),
    service: BillingService = Depends(get_billing_service),
) -> UsageConsumeResponse:
    return service.consume_usage(payload, request_source=context.source)


@router.post("/usage/check-and-consume", response_model=CheckAndConsumeResponse)
def check_and_consume_usage(
    payload: CheckAndConsumeRequest,
    context: InternalRequestContext = Depends(verify_internal_request),
    service: BillingService = Depends(get_billing_service),
) -> CheckAndConsumeResponse:
    return service.check_and_consume_usage(payload, request_source=context.source)
