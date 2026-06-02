from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.models import Feature, PlanFeature, TenantSubscription, UsageCounter, UsageEvent
from app.billing.schemas import (
    CheckAndConsumeRequest,
    CheckAndConsumeResponse,
    EntitlementCheckRequest,
    EntitlementCheckResponse,
    TenantFeatureStatus,
    TenantStatusResponse,
    TenantSubscriptionStatus,
    UsageConsumeRequest,
    UsageConsumeResponse,
)


ACTIVE_SUBSCRIPTION_STATUSES = {"trialing", "active"}


class BillingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_tenant_status(self, tenant_id: UUID) -> TenantStatusResponse | None:
        subscription = self.get_subscription_for_tenant(tenant_id)
        if subscription is None:
            return None

        period_key = current_period_key()
        features: dict[str, TenantFeatureStatus] = {}
        for plan_feature in subscription.plan.features:
            feature = plan_feature.feature
            used = None
            remaining = None
            if feature.type == "monthly_usage":
                counter = self.get_usage_counter(tenant_id, feature.key, period_key)
                used = counter.used if counter else 0
                remaining = calculate_remaining(plan_feature.limit_value, used)

            features[feature.key] = TenantFeatureStatus(
                enabled=plan_feature.enabled,
                limit=plan_feature.limit_value,
                used=used,
                remaining=remaining,
                reset_period=plan_feature.reset_period,
            )

        return TenantStatusResponse(
            tenant_id=tenant_id,
            status=subscription.status,
            subscription=TenantSubscriptionStatus(
                plan=subscription.plan.code,
                plan_name=subscription.plan.name,
                status=subscription.status,
                current_period_start=subscription.current_period_start,
                current_period_end=subscription.current_period_end,
            ),
            features=features,
        )

    def check_entitlement(self, request: EntitlementCheckRequest) -> EntitlementCheckResponse:
        return self._check_entitlement(request, period_key=current_period_key())

    def _check_entitlement(self, request: EntitlementCheckRequest, period_key: str) -> EntitlementCheckResponse:
        subscription = self.get_subscription_for_tenant(request.tenant_id)
        if subscription is None:
            return self._denied(
                request.feature_key,
                reason="subscription_not_found",
                message="El tenant no tiene una suscripcion registrada.",
                subscription_status=None,
            )

        if subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
            return self._denied(
                request.feature_key,
                reason="subscription_inactive",
                message="La suscripcion del tenant no esta activa.",
                subscription_status=subscription.status,
            )

        feature = self.get_feature(request.feature_key)
        if feature is None:
            return self._denied(
                request.feature_key,
                reason="feature_not_found",
                message="La funcionalidad no existe en el catalogo.",
                subscription_status=subscription.status,
            )

        plan_feature = self.get_plan_feature(subscription.plan_id, request.feature_key)
        if plan_feature is None or not plan_feature.enabled:
            return self._denied(
                request.feature_key,
                reason="feature_not_enabled",
                message="La funcionalidad no esta habilitada para el plan actual.",
                subscription_status=subscription.status,
                limit=plan_feature.limit_value if plan_feature else None,
                used=0,
            )

        if feature.type == "boolean":
            return self._allowed(request.feature_key, subscription.status)

        if feature.type == "monthly_usage":
            counter = self.get_usage_counter(request.tenant_id, request.feature_key, period_key)
            used = counter.used if counter else 0
            limit_value = plan_feature.limit_value
            remaining = calculate_remaining(limit_value, used)
            if limit_value is not None and used + request.amount > limit_value:
                return self._denied(
                    request.feature_key,
                    reason="quota_exceeded",
                    message="Limite mensual alcanzado para esta funcionalidad.",
                    subscription_status=subscription.status,
                    limit=limit_value,
                    used=used,
                    remaining=remaining,
                    upgrade_required=True,
                )
            return self._allowed(
                request.feature_key,
                subscription.status,
                limit=limit_value,
                used=used,
                remaining=calculate_remaining(limit_value, used),
            )

        if feature.type == "resource_limit":
            limit_value = plan_feature.limit_value
            used = request.resource_count
            if limit_value is not None:
                if used is None:
                    return self._denied(
                        request.feature_key,
                        reason="resource_limit_exceeded",
                        message="resource_count es requerido para validar este limite.",
                        subscription_status=subscription.status,
                        limit=limit_value,
                        used=None,
                        remaining=None,
                        upgrade_required=True,
                    )
                if used > limit_value:
                    return self._denied(
                        request.feature_key,
                        reason="resource_limit_exceeded",
                        message="Limite de recursos alcanzado para esta funcionalidad.",
                        subscription_status=subscription.status,
                        limit=limit_value,
                        used=used,
                        remaining=calculate_remaining(limit_value, used),
                        upgrade_required=True,
                    )
            return self._allowed(
                request.feature_key,
                subscription.status,
                limit=limit_value,
                used=used,
                remaining=calculate_remaining(limit_value, used or 0),
            )

        return self._denied(
            request.feature_key,
            reason="feature_not_found",
            message="Tipo de funcionalidad no soportado.",
            subscription_status=subscription.status,
        )

    def consume_usage(self, request: UsageConsumeRequest, request_source: str) -> UsageConsumeResponse:
        existing = self.get_usage_event(request.tenant_id, request.feature_key, request.idempotency_key)
        if existing is not None:
            return self._usage_response_for_existing_event(existing)

        try:
            response = self._record_usage(request, request_source)
            self.db.commit()
            return response
        except IntegrityError:
            self.db.rollback()
            existing = self.get_usage_event(request.tenant_id, request.feature_key, request.idempotency_key)
            if existing is None:
                raise
            return self._usage_response_for_existing_event(existing)

    def check_and_consume_usage(
        self,
        request: CheckAndConsumeRequest,
        request_source: str,
    ) -> CheckAndConsumeResponse:
        existing = self.get_usage_event(request.tenant_id, request.feature_key, request.idempotency_key)
        if existing is not None:
            usage = self._usage_response_for_existing_event(existing)
            subscription = self.get_subscription_for_tenant(request.tenant_id)
            return CheckAndConsumeResponse(
                allowed=True,
                reason="allowed",
                feature_key=request.feature_key,
                recorded=False,
                already_recorded=True,
                period_key=usage.period_key,
                used=usage.used,
                limit=usage.limit,
                remaining=usage.remaining,
                subscription_status=subscription.status if subscription else None,
            )

        occurred_at = ensure_utc(request.occurred_at or utc_now())
        check = self._check_entitlement(
            EntitlementCheckRequest(
                tenant_id=request.tenant_id,
                feature_key=request.feature_key,
                amount=request.amount,
                resource_count=request.resource_count,
                context=request.context,
            ),
            period_key=period_key_for(occurred_at),
        )
        if not check.allowed:
            return CheckAndConsumeResponse(
                allowed=False,
                reason=check.reason,
                feature_key=check.feature_key,
                message=check.message,
                recorded=False,
                already_recorded=False,
                used=check.used,
                limit=check.limit,
                remaining=check.remaining,
                subscription_status=check.subscription_status,
                upgrade_required=check.upgrade_required,
            )

        try:
            usage = self._record_usage(request, request_source)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.get_usage_event(request.tenant_id, request.feature_key, request.idempotency_key)
            if existing is None:
                raise
            usage = self._usage_response_for_existing_event(existing)
            usage.recorded = False
            usage.already_recorded = True

        return CheckAndConsumeResponse(
            allowed=True,
            reason="allowed",
            feature_key=request.feature_key,
            recorded=usage.recorded,
            already_recorded=usage.already_recorded,
            period_key=usage.period_key,
            used=usage.used,
            limit=usage.limit,
            remaining=usage.remaining,
            subscription_status=check.subscription_status,
        )

    def get_subscription_for_tenant(self, tenant_id: UUID) -> TenantSubscription | None:
        return self.db.scalar(
            select(TenantSubscription)
            .where(TenantSubscription.tenant_id == str(tenant_id))
            .order_by(TenantSubscription.created_at.desc(), TenantSubscription.id.desc())
        )

    def get_plan_feature(self, plan_id: int, feature_key: str) -> PlanFeature | None:
        return self.db.scalar(
            select(PlanFeature)
            .join(Feature)
            .where(PlanFeature.plan_id == plan_id, Feature.key == feature_key)
        )

    def get_feature(self, feature_key: str) -> Feature | None:
        return self.db.scalar(select(Feature).where(Feature.key == feature_key))

    def get_usage_counter(self, tenant_id: UUID, feature_key: str, period_key: str) -> UsageCounter | None:
        return self.db.scalar(
            select(UsageCounter).where(
                UsageCounter.tenant_id == str(tenant_id),
                UsageCounter.feature_key == feature_key,
                UsageCounter.period_key == period_key,
            )
        )

    def get_usage_event(self, tenant_id: UUID, feature_key: str, idempotency_key: str) -> UsageEvent | None:
        return self.db.scalar(
            select(UsageEvent).where(
                UsageEvent.tenant_id == str(tenant_id),
                UsageEvent.feature_key == feature_key,
                UsageEvent.idempotency_key == idempotency_key,
            )
        )

    def _record_usage(self, request: UsageConsumeRequest, request_source: str) -> UsageConsumeResponse:
        occurred_at = ensure_utc(request.occurred_at or utc_now())
        period_key = period_key_for(occurred_at)
        source = request.source or request_source
        limit_value = self._current_monthly_limit(request.tenant_id, request.feature_key)

        counter = self.get_usage_counter(request.tenant_id, request.feature_key, period_key)
        if counter is None:
            counter = UsageCounter(
                tenant_id=str(request.tenant_id),
                feature_key=request.feature_key,
                period_key=period_key,
                used=0,
                limit_value=limit_value,
            )
            self.db.add(counter)
        else:
            counter.limit_value = limit_value

        event = UsageEvent(
            tenant_id=str(request.tenant_id),
            feature_key=request.feature_key,
            amount=request.amount,
            source=source,
            external_id=request.external_id,
            idempotency_key=request.idempotency_key,
            occurred_at=occurred_at,
            period_key=period_key,
            event_metadata=request.metadata or None,
        )
        self.db.add(event)
        counter.used += request.amount
        counter.updated_at = utc_now()
        self.db.flush()

        return UsageConsumeResponse(
            recorded=True,
            already_recorded=False,
            feature_key=request.feature_key,
            period_key=period_key,
            used=counter.used,
            limit=counter.limit_value,
            remaining=calculate_remaining(counter.limit_value, counter.used),
        )

    def _usage_response_for_existing_event(self, event: UsageEvent) -> UsageConsumeResponse:
        counter = self.db.scalar(
            select(UsageCounter).where(
                UsageCounter.tenant_id == event.tenant_id,
                UsageCounter.feature_key == event.feature_key,
                UsageCounter.period_key == event.period_key,
            )
        )
        if counter is None:
            limit_value = self._current_monthly_limit(UUID(event.tenant_id), event.feature_key)
            used = 0
        else:
            limit_value = counter.limit_value
            used = counter.used

        return UsageConsumeResponse(
            recorded=False,
            already_recorded=True,
            feature_key=event.feature_key,
            period_key=event.period_key,
            used=used,
            limit=limit_value,
            remaining=calculate_remaining(limit_value, used),
        )

    def _current_monthly_limit(self, tenant_id: UUID, feature_key: str) -> int | None:
        subscription = self.get_subscription_for_tenant(tenant_id)
        if subscription is None or subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES:
            return None
        plan_feature = self.get_plan_feature(subscription.plan_id, feature_key)
        if plan_feature is None or plan_feature.feature.type != "monthly_usage":
            return None
        return plan_feature.limit_value

    def _allowed(
        self,
        feature_key: str,
        subscription_status: str,
        limit: int | None = None,
        used: int | None = None,
        remaining: int | None = None,
    ) -> EntitlementCheckResponse:
        return EntitlementCheckResponse(
            allowed=True,
            reason="allowed",
            feature_key=feature_key,
            limit=limit,
            used=used,
            remaining=remaining,
            subscription_status=subscription_status,
        )

    def _denied(
        self,
        feature_key: str,
        reason: str,
        message: str,
        subscription_status: str | None,
        limit: int | None = None,
        used: int | None = None,
        remaining: int | None = None,
        upgrade_required: bool = False,
    ) -> EntitlementCheckResponse:
        return EntitlementCheckResponse(
            allowed=False,
            reason=reason,
            message=message,
            feature_key=feature_key,
            limit=limit,
            used=used,
            remaining=remaining,
            subscription_status=subscription_status,
            upgrade_required=upgrade_required,
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def period_key_for(value: datetime) -> str:
    value = ensure_utc(value)
    return f"{value.year:04d}-{value.month:02d}"


def current_period_key() -> str:
    return period_key_for(utc_now())


def calculate_remaining(limit_value: int | None, used: int | None) -> int | None:
    if limit_value is None or used is None:
        return None
    return max(limit_value - used, 0)
