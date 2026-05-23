# Postas AI API

API stateless de IA para procesar una imagen publica de un `DocumentExtraction`.
No guarda extracciones ni usos en base de datos: recibe el modelo desde la API
principal, descarga la imagen de `file_url`, llama al proveedor IA configurado y
devuelve el mismo modelo con estado/datos actualizados mas un bloque `usage`
para que el backend principal registre el consumo por tenant.

Documentacion completa del flujo, payloads y uso:
[docs/document-extraction-flow.md](docs/document-extraction-flow.md).

## Flujo

1. La API principal de Postas valida tenant, permisos, plan y limites.
2. Postas crea o actualiza su `DocumentExtraction` y llama a esta API con el
   payload del modelo.
3. Esta API valida token/origen, descarga `file_url`, procesa la imagen con IA y
   responde `completed`, `needs_review` o `failed`.
4. Postas persiste la respuesta y registra `usage` donde corresponda.

## Endpoints

- `GET /api/v1/health`
- `POST /api/v1/document-extractions/process`
- `POST /api/v1/invoices/extract` como alias compatible

## Seguridad

Si `POSTAS_AI_API_TOKEN` esta configurado, cada request de procesamiento debe
enviar el mismo valor en `X-Postas-AI-Token` o en `Authorization: Bearer`.

Para identificar el origen de la request, enviar `X-Postas-Source`. Si
`ALLOWED_REQUEST_SOURCES` tiene una lista separada por coma, el origen debe estar
incluido.

## Ejemplo

```bash
curl -X POST http://localhost:8001/api/v1/document-extractions/process \
  -H "Content-Type: application/json" \
  -H "X-Postas-AI-Token: local-secret" \
  -H "X-Postas-Source: postas_api" \
  -d '{
    "uuid": "00000000-0000-0000-0000-000000000123",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "file_url": "https://example.com/invoice.png",
    "status": "pending",
    "raw_response": null,
    "extracted_data": null,
    "confidence": null,
    "attempts": 0,
    "error_message": null,
    "created_at": "2026-05-23T12:00:00Z",
    "updated_at": "2026-05-23T12:00:00Z",
    "processing_started_at": null,
    "completed_at": null,
    "confirmed_at": null
  }'
```

Respuesta resumida:

```json
{
  "uuid": "00000000-0000-0000-0000-000000000123",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "file_url": "https://example.com/invoice.png",
  "status": "completed",
  "raw_response": {},
  "extracted_data": {
    "is_invoice": true,
    "products": [],
    "date": "2026-05-23",
    "total": 1000,
    "confidence": 0.91
  },
  "confidence": 0.91,
  "attempts": 1,
  "error_message": null,
  "processing_started_at": "2026-05-23T12:00:01Z",
  "completed_at": "2026-05-23T12:00:02Z",
  "usage": {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "document_extraction_uuid": "00000000-0000-0000-0000-000000000123",
    "source": "postas_api",
    "feature": "document_extraction",
    "provider": "google_genai",
    "model": "gemini-2.5-flash-lite",
    "status": "completed",
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": 0,
    "confidence": 0.91,
    "attempts": 1
  }
}
```

`status` de respuesta usa los valores del modelo Django:

- `completed`: extraccion aceptada.
- `needs_review`: extraccion posible, pero requiere revision.
- `failed`: error tecnico o confidence menor que `MINIMUM_CONFIDENCE_THRESHOLD`.

Tambien acepta `image_url` o `signed_image_url` como alias de `file_url`, y
`tenant`, `tenant_uuid` o `tenantId` como alias de `tenant_id`.

## Proveedores IA

Los proveedores implementan `AIInvoiceProvider` en `app/providers/base.py`.

Incluidos:

- `google_genai` / `gemini`: implementacion real basada en Gemini.
- `mock`: proveedor deterministico para probar API sin llamar IA externa.

Para agregar otro proveedor, crear una clase que implemente `extract_invoice()`
y registrarla en `app/providers/registry.py`.

## Configuracion

Crear `.env` desde `.env.example`:

```bash
copy .env.example .env
```

Variables principales:

- `POSTAS_AI_API_TOKEN`
- `REQUIRE_API_TOKEN`
- `ALLOWED_REQUEST_SOURCES`
- `GOOGLE_API_KEY`
- `AI_PROVIDER`
- `GOOGLE_MODEL`
- `IMAGE_DOWNLOAD_TIMEOUT_SECONDS`
- `MAX_IMAGE_BYTES`
- `ACCEPTED_CONFIDENCE_THRESHOLD`
- `MINIMUM_CONFIDENCE_THRESHOLD`
- `INPUT_TOKEN_COST_PER_MILLION`
- `OUTPUT_TOKEN_COST_PER_MILLION`

## Ejecutar local

Con Docker:

```bash
docker compose up --build
```

Con entorno local:

```bash
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\env\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Para probar sin API key:

```bash
$env:AI_PROVIDER="mock"
.\env\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```
