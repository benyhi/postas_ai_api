from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.arca.crypto import CredentialCipher
from app.arca.models import ArcaInvoice
from app.arca.schemas import FiscalProfileWrite, InvoiceCreateRequest
from app.arca.service import FiscalProfileService, InvoiceService
from app.billing.models import Plan, TenantSubscription
from app.billing.seed import seed_billing_catalog
from app.core.config import get_settings
from app.db.base import Base


DATABASE_URL = os.getenv("ARCA_POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="ARCA PostgreSQL concurrency checks require ARCA_POSTGRES_TEST_DATABASE_URL",
)
CUIT = "20111111112"


class CoordinatedBilling:
    def __init__(self):
        self.last = 10
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self.created: list[int] = []

    def getLastVoucher(self, point_of_sale, voucher_type):
        with self._lock:
            return self.last

    def createVoucher(self, payload, return_response=False):
        number = payload["CbteDesde"]
        if number == 11 and not self.started.is_set():
            self.started.set()
            assert self.release.wait(timeout=10)
        with self._lock:
            self.last = number
            self.created.append(number)
        return {
            "FeDetResp": {
                "FECAEDetResponse": {
                    "Resultado": "A",
                    "CAE": f"700000000000{number}",
                    "CAEFchVto": "20260815",
                }
            }
        }

    def getVoucherInfo(self, number, point_of_sale, voucher_type):
        raise RuntimeError("(602) Comprobante no encontrado")


class FakeClient:
    def __init__(self, billing):
        self.ElectronicBilling = billing


def _credentials():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "PostgreSQL ARCA Test"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, f"CUIT {CUIT}"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
    )


def _invoice(external_id: str) -> InvoiceCreateRequest:
    return InvoiceCreateRequest.model_validate(
        {
            "external_id": external_id,
            "sale_id": str(uuid4()),
            "receiver": {"doc_type": 99, "doc_number": "0", "iva_condition_id": 5},
            "items": [{"description": "Producto", "quantity": "1", "final_unit_price": "121.00"}],
        }
    )


def test_postgresql_advisory_lock_and_reservation_prevent_duplicate_correlatives(monkeypatch):
    schema = f"arca_test_{uuid4().hex}"
    admin_engine = create_engine(DATABASE_URL)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        DATABASE_URL,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_size=5,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    keyring_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ARCA_CREDENTIAL_MASTER_KEYS", json.dumps({"postgres-test": keyring_key}))
    monkeypatch.setenv("ARCA_CREDENTIAL_ACTIVE_KEY_ID", "postgres-test")
    get_settings.cache_clear()
    billing = CoordinatedBilling()

    try:
        Base.metadata.create_all(engine)
        tenant_id = uuid4()
        with factory() as db:
            seed_billing_catalog(db)
            plan = db.scalar(select(Plan).where(Plan.code == "business"))
            now = datetime.now(timezone.utc)
            db.add(
                TenantSubscription(
                    tenant_id=str(tenant_id),
                    plan_id=plan.id,
                    status="active",
                    current_period_start=now - timedelta(days=1),
                    current_period_end=now + timedelta(days=30),
                )
            )
            db.commit()
            cert, private_key = _credentials()
            profile_service = FiscalProfileService(
                db,
                cipher=CredentialCipher.from_settings(get_settings()),
                client_factory=lambda _options: FakeClient(billing),
            )
            profile = profile_service.upsert(
                tenant_id,
                "development",
                FiscalProfileWrite(
                    arca_cuit=CUIT,
                    certificate=cert,
                    private_key=private_key,
                    access_token="postgres-test-token",
                    point_of_sale=1,
                    automatic_voucher_type=6,
                ),
            )
            profile.validation_status = "valid"
            db.commit()
            first = InvoiceService(db, profile_service=profile_service).enqueue(
                tenant_id, "development", _invoice("postgres-first")
            )
            second = InvoiceService(db, profile_service=profile_service).enqueue(
                tenant_id, "development", _invoice("postgres-second")
            )

        def process(invoice_id: int):
            with factory() as db:
                profile_service = FiscalProfileService(db, client_factory=lambda _options: FakeClient(billing))
                return InvoiceService(db, profile_service=profile_service).process(db.get(ArcaInvoice, invoice_id))

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(process, first.id)
            assert billing.started.wait(timeout=10)
            second_response = process(second.id)
            billing.release.set()
            first_response = first_future.result(timeout=10)

        assert first_response.status == "approved"
        assert first_response.voucher_number == 11
        assert second_response.status == "retrying"
        assert second_response.error.code == "sequence_busy"
        completed_second = process(second.id)
        assert completed_second.status == "approved"
        assert completed_second.voucher_number == 12
        assert billing.created == [11, 12]
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
        get_settings.cache_clear()
