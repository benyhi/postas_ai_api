# Document extraction flow

Esta guia documenta el flujo completo entre `postas_api` y `postas_ai_api` para
extraer informacion desde una imagen publica y registrar el consumo por tenant.

## Objetivo

`postas_ai_api` es una API stateless. No guarda datos en base de datos. Su unica
responsabilidad es:

1. Validar que la llamada venga desde un origen autorizado.
2. Descargar la imagen desde `file_url`.
3. Enviar la imagen al proveedor IA configurado.
4. Normalizar la respuesta.
5. Devolver el `DocumentExtraction` actualizado y un bloque `usage`.

`postas_api` sigue siendo el sistema dueño de la persistencia. Debe crear el
`DocumentExtraction`, subir la imagen, llamar a `postas_ai_api`, guardar la
respuesta y registrar o acumular el consumo de `usage`.

## Componentes

- `postas_api`: API principal Django. Maneja usuarios, tenants, permisos,
  uploads, persistencia y auditoria.
- `postas_ai_api`: API FastAPI. Procesa una imagen por URL y devuelve datos
  extraidos.
- Proveedor IA: `google_genai` en produccion o `mock` para pruebas locales.
- Almacenamiento publico o firmado: `file_url` debe ser accesible por
  `postas_ai_api` usando HTTP o HTTPS.

## Configuracion

En `D:\benja\proyectos\postas_api\.env`:

```env
AI_EXTRACTOR_BASE_URL=http://localhost:8001/api/v1
AI_EXTRACTOR_TOKEN=un-token-largo-random
AI_EXTRACTOR_SOURCE=postas_api
AI_EXTRACTOR_TIMEOUT=90
```

En `D:\benja\proyectos\postas_ai_api\.env`:

```env
POSTAS_AI_API_TOKEN=un-token-largo-random
REQUIRE_API_TOKEN=true
ALLOWED_REQUEST_SOURCES=postas_api
AI_PROVIDER=google_genai
GOOGLE_API_KEY=tu-api-key-google
```

Para probar sin llamar a Gemini:

```env
AI_PROVIDER=mock
```

`AI_EXTRACTOR_TOKEN` y `POSTAS_AI_API_TOKEN` deben tener exactamente el mismo
valor. Es un secreto compartido entre servicios, no un JWT de usuario.

## Seguridad

`postas_api` envia:

```http
Authorization: Bearer un-token-largo-random
X-Postas-Source: postas_api
Content-Type: application/json
Accept: application/json
```

`postas_ai_api` valida:

- El token contra `POSTAS_AI_API_TOKEN`.
- El origen contra `ALLOWED_REQUEST_SOURCES`, si esta configurado.

Si el token es invalido, responde `401`. Si el origen no esta permitido,
responde `403`.

## Endpoints

Endpoint principal:

```http
POST /api/v1/document-extractions/process
```

Alias compatible:

```http
POST /api/v1/invoices/extract
```

Healthcheck:

```http
GET /api/v1/health
```

## Flujo end to end

1. Un usuario en `postas_api` sube una imagen al endpoint de documentos.
2. `postas_api` valida tenant, permisos, extension, tamano y cuota mensual.
3. `postas_api` crea un `DocumentExtraction` en estado `pending`.
4. `postas_api` sube la imagen al almacenamiento configurado.
5. `postas_api` obtiene una URL publica o firmada para lectura.
6. `postas_api` marca la extraccion como `calling_ai` e incrementa `attempts`.
7. `postas_api` llama a `postas_ai_api` con el payload del `DocumentExtraction`.
8. `postas_ai_api` valida token y origen.
9. `postas_ai_api` descarga `file_url`.
10. `postas_ai_api` llama al proveedor IA.
11. `postas_ai_api` devuelve el documento con `status`, `raw_response`,
    `extracted_data`, `confidence`, timestamps y `usage`.
12. `postas_api` persiste la respuesta y deja el documento en `completed`,
    `needs_review` o `failed`.

## Request desde cliente a postas_api

El cliente final no llama directamente a `postas_ai_api`. Debe llamar a
`postas_api` con autenticacion de usuario.

```http
POST http://localhost:8000/api/v1/document-extractions/
Authorization: Bearer <jwt-de-postas-api>
Content-Type: multipart/form-data
```

Campos:

| Campo | Tipo | Requerido | Descripcion |
| --- | --- | --- | --- |
| `image` | file | Si | Imagen `.jpg`, `.jpeg` o `.png`. |
| `provider` | string | No | `mock`, `google_genai` o proveedor registrado. |
| `metadata` | object/string JSON | No | Datos auxiliares del origen de la carga. |

Ejemplo con PowerShell:

```powershell
$jwt = "<jwt-de-postas-api>"
$form = @{
  image = Get-Item "D:\tmp\factura.png"
  provider = "mock"
  metadata = '{"source_screen":"manual_test"}'
}

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/document-extractions/" `
  -Method Post `
  -Headers @{ Authorization = "Bearer $jwt" } `
  -Form $form
```

## Request de postas_api a postas_ai_api

`postas_api` construye un payload JSON basado en el modelo
`DocumentExtraction`.

```json
{
  "uuid": "00000000-0000-0000-0000-000000000123",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "file_url": "https://cdn.example.com/signed/document.png",
  "status": "calling_ai",
  "raw_response": null,
  "extracted_data": null,
  "confidence": null,
  "attempts": 1,
  "error_message": null,
  "created_at": "2026-05-23T12:00:00Z",
  "updated_at": "2026-05-23T12:00:01Z",
  "processing_started_at": "2026-05-23T12:00:01Z",
  "completed_at": null,
  "confirmed_at": null,
  "provider": "mock",
  "metadata": {
    "source": "postas_api",
    "stored_file_url": "https://cdn.example.com/document.png",
    "file_key": "tenant/document-extractions/document.png",
    "source_screen": "manual_test"
  }
}
```

Campos principales:

| Campo | Tipo | Requerido | Descripcion |
| --- | --- | --- | --- |
| `uuid` | UUID | Si | ID del `DocumentExtraction` creado por `postas_api`. |
| `tenant_id` | string/UUID | Si | Tenant dueño de la extraccion. |
| `file_url` | URL | Si | URL publica o firmada que la IA puede descargar. |
| `status` | string | Si | Normalmente `calling_ai` cuando llega a la IA. |
| `attempts` | int | Si | Intentos acumulados en `postas_api`. |
| `provider` | string | No | Fuerza proveedor IA. Si falta, usa `AI_PROVIDER`. |
| `metadata` | object | No | Contexto para trazabilidad. |

Aliases aceptados por compatibilidad:

- `signed_image_url` o `image_url` funcionan como `file_url`.
- `document_extraction_id` funciona como `uuid`.
- `tenant`, `tenant_uuid` o `tenantId` funcionan como `tenant_id`.

## Response de postas_ai_api

Respuesta exitosa con proveedor `mock`:

```json
{
  "uuid": "00000000-0000-0000-0000-000000000123",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "file_url": "https://cdn.example.com/signed/document.png",
  "status": "completed",
  "raw_response": {
    "is_invoice": true,
    "products": [
      {
        "code": "MOCK-001",
        "description": "Producto de prueba",
        "quantity": 1.0,
        "price": 100.0,
        "total": 100.0
      }
    ],
    "date": null,
    "total": 100.0,
    "confidence": 0.9
  },
  "extracted_data": {
    "is_invoice": true,
    "products": [
      {
        "code": "MOCK-001",
        "description": "Producto de prueba",
        "quantity": 1.0,
        "price": 100.0,
        "total": 100.0
      }
    ],
    "date": null,
    "total": 100.0,
    "confidence": 0.9
  },
  "confidence": 0.9,
  "attempts": 1,
  "error_message": null,
  "created_at": "2026-05-23T12:00:00Z",
  "updated_at": "2026-05-23T12:00:02Z",
  "processing_started_at": "2026-05-23T12:00:01Z",
  "completed_at": "2026-05-23T12:00:02Z",
  "confirmed_at": null,
  "usage": {
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "document_extraction_uuid": "00000000-0000-0000-0000-000000000123",
    "source": "postas_api",
    "feature": "document_extraction",
    "provider": "mock",
    "model": "mock-invoice-extractor",
    "status": "completed",
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": 0.0,
    "confidence": 0.9,
    "latency_ms": 1,
    "attempts": 1,
    "error_message": null,
    "created_at": "2026-05-23T12:00:02Z",
    "extra": {
      "authenticated": true,
      "provider_attempts": [],
      "request_metadata": {
        "source": "postas_api"
      },
      "image": {
        "content_type": "image/png",
        "size_bytes": 100000
      }
    }
  }
}
```

Campos que `postas_api` debe persistir:

| Campo response | Campo en postas_api | Descripcion |
| --- | --- | --- |
| `raw_response` | `raw_response` | Respuesta cruda normalizada de la IA. |
| `extracted_data` | `extracted_data` | Datos finales para usar en UI o confirmacion. |
| `confidence` | `confidence` | Score decimal entre `0` y `1`. |
| `status` | `status` | Estado final del documento. |
| `usage` | `raw_usage` y campos de consumo | Tokens, costo, proveedor, modelo y latencia. |
| `usage.provider` | `provider` | Proveedor usado realmente. |
| `usage.model` | `model` | Modelo usado realmente. |
| `usage.total_tokens` | `total_tokens` | Total de tokens reportados por proveedor. |
| `usage.estimated_cost_usd` | `estimated_cost_usd` | Costo estimado segun config local. |

## Estados

Estados entrantes aceptados:

- `pending`
- `uploading`
- `processing`
- `calling_ai`
- `completed`
- `needs_review`
- `failed`
- `confirmed`
- `cancelled`

Estados finales relevantes devueltos por `postas_ai_api`:

- `completed`: la extraccion fue aceptada.
- `needs_review`: la extraccion existe, pero el score no llega al umbral de
  aceptacion.
- `failed`: error tecnico, URL invalida, token invalido o confidence menor al
  minimo.

Los umbrales se configuran en `postas_ai_api`:

```env
ACCEPTED_CONFIDENCE_THRESHOLD=0.85
MINIMUM_CONFIDENCE_THRESHOLD=0.60
```

## Errores comunes

Token invalido:

```json
{
  "detail": "Token de seguridad invalido"
}
```

Origen no permitido:

```json
{
  "detail": "Origen de request no permitido"
}
```

URL no publica o no descargable:

```json
{
  "status": "failed",
  "error_message": "..."
}
```

Proveedor no configurado:

```json
{
  "status": "failed",
  "error_message": "Falta configurar GOOGLE_API_KEY o API_KEY en el entorno/.env"
}
```

## Prueba directa contra postas_ai_api

Levantar la IA:

```powershell
cd D:\benja\proyectos\postas_ai_api
.\env\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

Enviar request:

```powershell
$token = "un-token-largo-random"
$body = @{
  uuid = "00000000-0000-0000-0000-000000000123"
  tenant_id = "00000000-0000-0000-0000-000000000001"
  file_url = "https://example.com/invoice.png"
  status = "pending"
  raw_response = $null
  extracted_data = $null
  confidence = $null
  attempts = 0
  error_message = $null
  created_at = "2026-05-23T12:00:00Z"
  updated_at = "2026-05-23T12:00:00Z"
  processing_started_at = $null
  completed_at = $null
  confirmed_at = $null
  metadata = @{ source = "manual_test" }
}

Invoke-RestMethod `
  -Uri "http://localhost:8001/api/v1/document-extractions/process" `
  -Method Post `
  -Headers @{
    Authorization = "Bearer $token"
    "X-Postas-Source" = "postas_api"
  } `
  -ContentType "application/json" `
  -Body ($body | ConvertTo-Json -Depth 10)
```

## Prueba del flujo completo

1. Levantar `postas_ai_api` en puerto `8001`.
2. Levantar `postas_api` en puerto `8000`.
3. Verificar que ambos `.env` usen el mismo token.
4. Hacer login en `postas_api`.
5. Subir una imagen a `POST /api/v1/document-extractions/`.
6. Confirmar que la respuesta incluya `status`, `confidence`, `products` y
   `error_message`.
7. Consultar el detalle de la extraccion en `postas_api` si hace falta.

Comandos base:

```powershell
cd D:\benja\proyectos\postas_ai_api
.\env\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

```powershell
cd D:\benja\proyectos\postas_api
.\env\Scripts\python.exe manage.py runserver 8000
```

## Notas de implementacion

- `postas_ai_api` no debe guardar nada en base de datos.
- `file_url` debe ser descargable desde donde corre `postas_ai_api`.
- `usage` es parte del contrato porque `postas_api` necesita registrar consumo
  por tenant.
- `provider=mock` permite validar integracion sin costo ni API key externa.
- `provider=google_genai` usa Gemini y requiere `GOOGLE_API_KEY`.
- El endpoint viejo `/api/v1/invoices/extract` existe solo como alias de
  compatibilidad. El endpoint recomendado es
  `/api/v1/document-extractions/process`.
