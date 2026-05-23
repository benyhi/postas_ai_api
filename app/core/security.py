import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class RequestContext:
    source: str
    authenticated: bool


def verify_request(request: Request) -> RequestContext:
    settings = get_settings()
    source = _extract_source(request, settings)

    if settings.allowed_request_sources and source not in settings.allowed_request_sources:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origen de request no permitido",
        )

    expected_token = settings.postas_ai_api_token
    if not expected_token:
        if settings.require_api_token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="POSTAS_AI_API_TOKEN no esta configurado",
            )
        return RequestContext(source=source, authenticated=False)

    received_token = _extract_token(request, settings)
    if not received_token or not secrets.compare_digest(received_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de seguridad invalido",
        )

    return RequestContext(source=source, authenticated=True)


def _extract_source(request: Request, settings: Settings) -> str:
    return (
        request.headers.get(settings.source_header_name)
        or request.headers.get("X-Request-Origin")
        or request.headers.get("X-Origin")
        or "unknown"
    )


def _extract_token(request: Request, settings: Settings) -> str | None:
    token = (
        request.headers.get(settings.token_header_name)
        or request.headers.get("X-Postas-Signature-Token")
        or request.headers.get("X-API-Token")
    )
    if token:
        return token.strip()

    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()
