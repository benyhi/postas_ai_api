from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.billing.models import Payment, Plan, TenantSubscription, UsageCounter, UsageEvent
from app.billing.seed import seed_billing_catalog
from app.db.session import SessionLocal

ACTIVE_SUBSCRIPTION_STATUSES = {"trialing", "active"}
PERIOD_DAYS = 30


@dataclass(frozen=True)
class PlanTenantRecord:
    plan_code: str
    tenant_id: str
    subscription_created: bool
    payment_created: bool


@dataclass(frozen=True)
class PlanTenantSeedResult:
    records: list[PlanTenantRecord]

    @property
    def created_subscriptions(self) -> int:
        return sum(1 for record in self.records if record.subscription_created)

    @property
    def created_payments(self) -> int:
        return sum(1 for record in self.records if record.payment_created)


def seed_plan_tenants(db: Session) -> PlanTenantSeedResult:
    seed_billing_catalog(db)

    plans = list(db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id)))
    existing_subscriptions = _active_subscriptions_by_plan(db)
    used_tenant_ids = _used_tenant_ids(db)
    next_tenant_int = _next_tenant_int(used_tenant_ids)
    now = datetime.now(timezone.utc)

    records: list[PlanTenantRecord] = []
    for plan in plans:
        subscription = existing_subscriptions.get(plan.code)
        subscription_created = False

        if subscription is None:
            tenant_id = _next_available_tenant_id(next_tenant_int, used_tenant_ids)
            next_tenant_int = tenant_id.int + 1
            period_end = now + timedelta(days=PERIOD_DAYS)
            subscription = TenantSubscription(
                tenant_id=str(tenant_id),
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                current_period_end=period_end,
            )
            db.add(subscription)
            db.flush()
            existing_subscriptions[plan.code] = subscription
            used_tenant_ids.add(tenant_id)
            subscription_created = True

        payment_created = _ensure_manual_payment(db, plan, subscription, now)
        records.append(
            PlanTenantRecord(
                plan_code=plan.code,
                tenant_id=subscription.tenant_id,
                subscription_created=subscription_created,
                payment_created=payment_created,
            )
        )

    db.commit()
    return PlanTenantSeedResult(records=records)


def _active_subscriptions_by_plan(db: Session) -> dict[str, TenantSubscription]:
    subscriptions = db.scalars(
        select(TenantSubscription)
        .join(Plan)
        .where(TenantSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES))
        .order_by(TenantSubscription.created_at.asc(), TenantSubscription.id.asc())
    )
    by_plan: dict[str, TenantSubscription] = {}
    for subscription in subscriptions:
        by_plan.setdefault(subscription.plan.code, subscription)
    return by_plan


def _used_tenant_ids(db: Session) -> set[UUID]:
    tenant_values: set[str] = set()
    for model in (TenantSubscription, Payment, UsageCounter, UsageEvent):
        tenant_values.update(str(value) for value in db.scalars(select(model.tenant_id)).all())
    return {tenant_id for value in tenant_values if (tenant_id := _parse_uuid(value)) is not None}


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _next_tenant_int(used_tenant_ids: set[UUID]) -> int:
    if not used_tenant_ids:
        return 1
    return max(tenant_id.int for tenant_id in used_tenant_ids) + 1


def _next_available_tenant_id(start: int, used_tenant_ids: set[UUID]) -> UUID:
    tenant_int = start
    while True:
        tenant_id = UUID(int=tenant_int)
        if tenant_id not in used_tenant_ids:
            return tenant_id
        tenant_int += 1


def _ensure_manual_payment(db: Session, plan: Plan, subscription: TenantSubscription, paid_at: datetime) -> bool:
    existing_payment = db.scalar(select(Payment).where(Payment.subscription_id == subscription.id))
    if existing_payment is not None:
        return False

    period_start = subscription.current_period_start
    period_end = subscription.current_period_end
    amount = plan.price_amount if plan.price_amount is not None else Decimal("0.00")
    payment = Payment(
        tenant_id=subscription.tenant_id,
        subscription_id=subscription.id,
        provider="manual",
        provider_payment_id=f"manual-{plan.code}-{subscription.tenant_id.replace('-', '')[-12:]}",
        provider_status="approved",
        amount=amount,
        currency=plan.currency,
        paid_at=paid_at,
        period_start=period_start,
        period_end=period_end,
        raw_payload={"source": "scripts/seed_plan_tenants.py", "plan_code": plan.code},
    )
    db.add(payment)
    return True


def main() -> None:
    with SessionLocal() as db:
        result = seed_plan_tenants(db)

    print("Tenants de planes aplicados:")
    for record in result.records:
        subscription_status = "creada" if record.subscription_created else "existente"
        payment_status = "pago creado" if record.payment_created else "pago existente"
        print(f"- {record.plan_code}: {record.tenant_id} ({subscription_status}, {payment_status})")
    print(
        f"Total: {len(result.records)} planes, "
        f"{result.created_subscriptions} suscripciones nuevas, "
        f"{result.created_payments} pagos nuevos."
    )


if __name__ == "__main__":
    main()
