from __future__ import annotations

import os

import pytest

from app.arca.client import ArcaClientOptions, create_arca_client
from app.arca.crypto import DecryptedCredentials, validate_credential_material


pytestmark = pytest.mark.skipif(
    os.getenv("ARCA_LIVE_TESTS") != "1",
    reason="ARCA live homologation checks are opt-in",
)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"Falta {name} para la prueba live de homologacion")
    return value


def test_homologation_credentials_can_query_wsfe_without_emitting():
    environment = os.getenv("ARCA_LIVE_ENVIRONMENT", "development").strip()
    assert environment == "development", "Las pruebas live solo pueden ejecutarse contra homologacion"

    cuit = _required("ARCA_LIVE_CUIT")
    certificate = _required("ARCA_LIVE_CERTIFICATE")
    private_key = _required("ARCA_LIVE_PRIVATE_KEY")
    access_token = _required("ARCA_LIVE_ACCESS_TOKEN")
    point_of_sale = int(_required("ARCA_LIVE_POINT_OF_SALE"))
    voucher_type = int(os.getenv("ARCA_LIVE_VOUCHER_TYPE", "6"))

    validate_credential_material(certificate, private_key, cuit)
    client = create_arca_client(
        ArcaClientOptions(
            cuit=cuit,
            environment=environment,
            credentials=DecryptedCredentials(certificate, private_key, access_token),
            timeout_seconds=float(os.getenv("ARCA_LIVE_TIMEOUT_SECONDS", "30")),
            production_calls_enabled=False,
        )
    )

    last = client.ElectronicBilling.getLastVoucher(point_of_sale, voucher_type)
    assert int(last or 0) >= 0
