# Postas Platform API

API de plataforma para el backoffice SaaS de Postas. En esta etapa el servicio
empieza a ser la fuente de verdad para billing: planes, features, limites,
suscripciones, pagos y consumo mensual por tenant.

La API legacy de procesamiento IA sigue disponible durante la transicion, pero
el nuevo modulo de plataforma vive en `/internal/v1`.

## Endpoints principales

- `GET /api/v1/health`
- `GET /internal/v1/tenants/{tenant_id}/status`
- `POST /internal/v1/entitlements/check`
- `POST /internal/v1/usage/consume`
- `POST /internal/v1/usage/check-and-consume`

Endpoints legacy de IA:

- `POST /api/v1/document-extractions/process`
- `POST /api/v1/invoices/extract`

## Configuracion

Crear `.env` desde `.env.example`:

```bash
copy .env.example .env
```

Variables principales:

- `APP_NAME`
- `API_PREFIX`
- `DATABASE_URL`
- `POSTAS_SERVICE_TOKEN`
- `ALLOWED_REQUEST_SOURCES`
- `POSTAS_INTERNAL_REQUIRE_TLS` (por defecto `true`)
- `ARCA_CREDENTIAL_MASTER_KEYS` (objeto JSON `key_id -> Fernet key`, sin fallback)
- `ARCA_CREDENTIAL_ACTIVE_KEY_ID`
- `ARCA_PRODUCTION_CALLS_ENABLED` (por defecto `false`)
- `ARCA_TIMEOUT_SECONDS`
- `ARCA_WORKER_POLL_SECONDS`
- `ARCA_WORKER_BATCH_SIZE`

Para la API legacy de IA tambien siguen disponibles:

- `POSTAS_AI_API_TOKEN`
- `REQUIRE_API_TOKEN`
- `GOOGLE_API_KEY`
- `AI_PROVIDER`
- `GOOGLE_MODEL`

## Base de datos

Por defecto se usa SQLite local:

```bash
sqlite:///./postas_platform.db
```

Aplicar migraciones:

```bash
.\env\Scripts\python.exe -m alembic upgrade head
```

## Seed de billing

El catalogo inicial de planes y features es idempotente:

```bash
.\env\Scripts\python.exe scripts\seed_billing.py
```

El plan `test` queda incluido en ese seed. Es privado y habilita todas las
features; las features de consumo mensual o limite de recursos quedan con
limite `1`.

Para crear tenants locales de prueba, uno por cada plan activo, ejecutar:

```bash
.\env\Scripts\python.exe scripts\seed_plan_tenants.py
```

El script reutiliza cualquier suscripcion activa existente para un plan y crea
los planes faltantes con UUIDs consecutivos al mayor tenant ya presente.

Documentacion del modulo:

- [docs/billing.md](docs/billing.md)
- [docs/arca_invoicing_service.txt](docs/arca_invoicing_service.txt)

## Facturacion ARCA

Los perfiles fiscales y las facturas viven bajo
`/internal/v1/arca/tenants/{tenant_id}`. Todas las llamadas requieren HTTPS,
`X-Postas-Source: postas_api` y `X-Postas-Service-Token`.

El worker fiscal es un proceso separado:

```bash
.\env\Scripts\python.exe -m app.arca.worker
```

El worker requiere PostgreSQL; no inicia sobre SQLite porque ese dialecto no
ofrece las garantias de `SKIP LOCKED` y advisory locks usadas por la secuencia.

`docker compose up --build` inicia tambien `arca_worker`. La reserva del numero
se persiste antes de llamar a ARCA; ante timeout o reinicio, el worker consulta
primero ese mismo comprobante y adopta un CAE existente.

No habilita produccion por tener un perfil productivo: la instancia tambien
debe configurar `ARCA_PRODUCTION_CALLS_ENABLED=true`.

## Ejecutar local

Con Docker:

```bash
docker compose up --build
```

Con entorno local:

```bash
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\env\Scripts\python.exe -m alembic upgrade head
.\env\Scripts\python.exe scripts\seed_billing.py
.\env\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

## Tests

```bash
.\env\Scripts\python.exe -m pytest tests/test_billing.py -q
.\env\Scripts\python.exe -m pytest tests/test_arca.py -q
```

`tests/test_arca_live.py` es opt-in, rechaza `production` y solo consulta WSFE
en homologacion; las variables necesarias estan documentadas en
`docs/arca_invoicing_service.txt`.
