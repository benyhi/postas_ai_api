from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.billing.models import Plan, TenantSubscription, UsageCounter, UsageEvent
from app.billing.schemas import EntitlementCheckRequest
from app.billing.seed import seed_billing_catalog
from app.billing.service import BillingService
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POSTAS_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("ALLOWED_REQUEST_SOURCES", "postas_api,postas_ai_api")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestingSessionLocal() as db:
        seed_billing_catalog(db)
        yield db

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    get_settings.cache_clear()


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    return TestClient(app)


def auth_headers(source: str = "postas_api") -> dict[str, str]:
    return {
        "X-Postas-Source": source,
        "X-Postas-Service-Token": "test-token",
    }


def create_subscription(db: Session, tenant_id: UUID, plan_code: str, status: str = "active") -> TenantSubscription:
    plan = db.scalar(select(Plan).where(Plan.code == plan_code))
    assert plan is not None
    now = datetime.now(timezone.utc)
    subscription = TenantSubscription(
        tenant_id=str(tenant_id),
        plan_id=plan.id,
        status=status,
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=30),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def test_seed_creates_plans_and_features_without_duplicates(db_session: Session) -> None:
    first_plan_count = db_session.scalar(select(func.count()).select_from(Plan))
    seed_billing_catalog(db_session)
    second_plan_count = db_session.scalar(select(func.count()).select_from(Plan))

    assert first_plan_count == 5
    assert second_plan_count == first_plan_count


def test_business_ai_can_use_document_extraction_when_quota_available(db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")

    response = BillingService(db_session).check_entitlement(
        EntitlementCheckRequest(tenant_id=tenant_id, feature_key="document_extraction", amount=1)
    )

    assert response.allowed is True
    assert response.reason == "allowed"
    assert response.limit == 100
    assert response.used == 0
    assert response.remaining == 100


def test_tenant_status_endpoint_returns_subscription_and_feature_usage(client: TestClient, db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")

    response = client.get(f"/internal/v1/tenants/{tenant_id}/status", headers=auth_headers("postas_api"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["subscription"]["plan"] == "business_ai"
    assert payload["features"]["document_extraction"]["enabled"] is True
    assert payload["features"]["document_extraction"]["limit"] == 100
    assert payload["features"]["document_extraction"]["used"] == 0


def test_business_ai_cannot_use_document_extraction_when_quota_is_exhausted(db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")
    db_session.add(
        UsageCounter(
            tenant_id=str(tenant_id),
            feature_key="document_extraction",
            period_key=datetime.now(timezone.utc).strftime("%Y-%m"),
            used=100,
            limit_value=100,
        )
    )
    db_session.commit()

    response = BillingService(db_session).check_entitlement(
        EntitlementCheckRequest(tenant_id=tenant_id, feature_key="document_extraction", amount=1)
    )

    assert response.allowed is False
    assert response.reason == "quota_exceeded"
    assert response.upgrade_required is True
    assert response.remaining == 0


def test_business_plan_cannot_use_document_extraction(db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business")

    response = BillingService(db_session).check_entitlement(
        EntitlementCheckRequest(tenant_id=tenant_id, feature_key="document_extraction", amount=1)
    )

    assert response.allowed is False
    assert response.reason == "feature_not_enabled"


def test_usage_consume_creates_event_and_counter(client: TestClient, db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")

    response = client.post(
        "/internal/v1/usage/consume",
        headers=auth_headers("postas_ai_api"),
        json={
            "tenant_id": str(tenant_id),
            "feature_key": "document_extraction",
            "amount": 1,
            "external_id": "doc-1",
            "idempotency_key": "document-extraction:doc-1",
            "occurred_at": "2026-05-27T23:10:00Z",
            "metadata": {"provider": "google_genai"},
        },
    )

    assert response.status_code == 200
    assert response.json()["recorded"] is True
    assert response.json()["used"] == 1
    assert db_session.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == "document-extraction:doc-1")) is not None
    counter = db_session.scalar(select(UsageCounter).where(UsageCounter.tenant_id == str(tenant_id)))
    assert counter is not None
    assert counter.used == 1
    assert counter.limit_value == 100


def test_usage_consume_is_idempotent(client: TestClient, db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")
    payload = {
        "tenant_id": str(tenant_id),
        "feature_key": "document_extraction",
        "amount": 1,
        "external_id": "doc-2",
        "idempotency_key": "document-extraction:doc-2",
        "occurred_at": "2026-05-27T23:10:00Z",
    }

    first = client.post("/internal/v1/usage/consume", headers=auth_headers("postas_ai_api"), json=payload)
    second = client.post("/internal/v1/usage/consume", headers=auth_headers("postas_ai_api"), json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["recorded"] is False
    assert second.json()["already_recorded"] is True
    counter = db_session.scalar(select(UsageCounter).where(UsageCounter.tenant_id == str(tenant_id)))
    assert counter is not None
    assert counter.used == 1


def test_check_and_consume_does_not_record_when_feature_is_disabled(client: TestClient, db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business")

    response = client.post(
        "/internal/v1/usage/check-and-consume",
        headers=auth_headers("postas_api"),
        json={
            "tenant_id": str(tenant_id),
            "feature_key": "document_extraction",
            "amount": 1,
            "external_id": "doc-3",
            "idempotency_key": "document-extraction:doc-3",
        },
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "feature_not_enabled"
    assert db_session.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == "document-extraction:doc-3")) is None


def test_check_and_consume_uses_occurred_at_period_for_quota(client: TestClient, db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "business_ai")
    db_session.add(
        UsageCounter(
            tenant_id=str(tenant_id),
            feature_key="document_extraction",
            period_key="2026-04",
            used=100,
            limit_value=100,
        )
    )
    db_session.commit()

    response = client.post(
        "/internal/v1/usage/check-and-consume",
        headers=auth_headers("postas_api"),
        json={
            "tenant_id": str(tenant_id),
            "feature_key": "document_extraction",
            "amount": 1,
            "external_id": "doc-4",
            "idempotency_key": "document-extraction:doc-4",
            "occurred_at": "2026-04-30T23:10:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason"] == "quota_exceeded"
    assert db_session.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == "document-extraction:doc-4")) is None


def test_resource_limit_denies_when_resource_count_exceeds_limit(db_session: Session) -> None:
    tenant_id = uuid4()
    create_subscription(db_session, tenant_id, "free")

    response = BillingService(db_session).check_entitlement(
        EntitlementCheckRequest(
            tenant_id=tenant_id,
            feature_key="products",
            amount=1,
            resource_count=21,
        )
    )

    assert response.allowed is False
    assert response.reason == "resource_limit_exceeded"
    assert response.limit == 20
    assert response.remaining == 0


def test_internal_security_rejects_requests_without_valid_token(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/entitlements/check",
        headers={"X-Postas-Source": "postas_api"},
        json={
            "tenant_id": str(uuid4()),
            "feature_key": "document_extraction",
            "amount": 1,
        },
    )

    assert response.status_code == 403
