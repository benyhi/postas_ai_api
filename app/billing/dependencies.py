import secrets
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.billing.service import BillingService
from app.core.config import Settings, get_settings
from app.db.session import get_db


@dataclass(frozen=True)
class InternalRequestContext:
    source: str
    authenticated: bool


def verify_internal_request(request: Request) -> InternalRequestContext:
    settings = get_settings()
    source = _extract_source(request, settings)

    if not settings.postas_service_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticacion interna no esta configurada",
        )
    if not settings.allowed_request_sources:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Los origenes internos permitidos no estan configurados",
        )
    if source not in settings.allowed_request_sources:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origen de request no permitido")

    if settings.internal_require_tls and request.url.scheme != "https":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TLS es obligatorio")

    expected_token = settings.postas_service_token
    received_token = request.headers.get(settings.service_token_header_name)
    if not received_token or not secrets.compare_digest(received_token.strip(), expected_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token de servicio invalido")

    return InternalRequestContext(source=source, authenticated=True)


def get_billing_service(db: Session = Depends(get_db)) -> BillingService:
    return BillingService(db)


def _extract_source(request: Request, settings: Settings) -> str:
    return request.headers.get(settings.service_source_header_name) or "unknown"
