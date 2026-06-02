# Billing & Plans

`postas_platform_api` es la fuente de verdad para planes, features, limites,
suscripciones, pagos y consumo mensual. En esta primera etapa no hay integracion
con MercadoPago, frontend ni cliente dentro de `postas_api`.

## Base de datos

Configurar `DATABASE_URL`. Por defecto se usa SQLite local:

```bash
sqlite:///./postas_platform.db
```

Aplicar migraciones:

```bash
alembic upgrade head
```

## Seed inicial

El catalogo de planes y features se carga de forma idempotente:

```bash
python scripts/seed_billing.py
```

El seed actualiza planes, features y configuraciones `PlanFeature` existentes
sin duplicar registros.

## Seguridad interna

Los endpoints internos viven bajo `/internal/v1`.

Headers:

- `X-Postas-Source`
- `X-Postas-Service-Token`

Variables:

- `POSTAS_SERVICE_TOKEN`
- `ALLOWED_REQUEST_SOURCES`, separado por coma.

Si `POSTAS_SERVICE_TOKEN` esta configurado, el token debe coincidir. Si
`ALLOWED_REQUEST_SOURCES` esta configurado, `X-Postas-Source` debe estar en la
lista. Los fallos devuelven `403`.

## Endpoints

- `GET /internal/v1/tenants/{tenant_id}/status`
- `POST /internal/v1/entitlements/check`
- `POST /internal/v1/usage/consume`
- `POST /internal/v1/usage/check-and-consume`

Si un tenant no tiene suscripcion, el status endpoint devuelve `404` con
`detail: "subscription_not_found"`. Los checks devuelven `allowed: false` y
`reason: "subscription_not_found"`.

## Ejemplos curl

```bash
curl http://localhost:8001/internal/v1/tenants/00000000-0000-0000-0000-000000000001/status \
  -H "X-Postas-Source: postas_api" \
  -H "X-Postas-Service-Token: local-service-token"
```

```bash
curl -X POST http://localhost:8001/internal/v1/entitlements/check \
  -H "Content-Type: application/json" \
  -H "X-Postas-Source: postas_api" \
  -H "X-Postas-Service-Token: local-service-token" \
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "feature_key": "document_extraction",
    "amount": 1,
    "resource_count": null,
    "context": {"source": "document_extraction"}
  }'
```

```bash
curl -X POST http://localhost:8001/internal/v1/usage/consume \
  -H "Content-Type: application/json" \
  -H "X-Postas-Source: postas_ai_api" \
  -H "X-Postas-Service-Token: local-service-token" \
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "feature_key": "document_extraction",
    "amount": 1,
    "external_id": "document_extraction_uuid",
    "idempotency_key": "document-extraction:document_extraction_uuid",
    "metadata": {"provider": "google_genai", "model": "gemini-2.5-flash-lite"}
  }'
```

```bash
curl -X POST http://localhost:8001/internal/v1/usage/check-and-consume \
  -H "Content-Type: application/json" \
  -H "X-Postas-Source: postas_api" \
  -H "X-Postas-Service-Token: local-service-token" \
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "feature_key": "document_extraction",
    "amount": 1,
    "external_id": "document_extraction_uuid",
    "idempotency_key": "document-extraction:document_extraction_uuid"
  }'
```

## TODOs

- Agregar endpoints admin cuando exista autenticacion/roles admin.
- Crear cliente interno en `postas_api` para consultar permisos y registrar
  consumos.
