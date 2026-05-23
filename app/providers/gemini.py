import json
import re
import time
from typing import Any

from app.core.config import get_settings
from app.providers.base import AIInvoiceProvider, ProviderInvoiceResult, ProviderUsage
from app.schemas import InvoiceData


SYSTEM_PROMPT = """
You are an invoice extraction service. Analyze the invoice image and extract
products, amounts, total, invoice date and a confidence score.

Invoice layouts can vary. Product/service rows usually contain fields like:
Codigo/Code, Descripcion/Description, Cantidad/Quantity/Units, Precio/Price,
Subtotal or Total. Do not invent information. If a value is unclear or missing,
return null. If the image is not an invoice, return is_invoice=false and an
empty products array.
"""

USER_PROMPT = """
Analyze this invoice image and return only valid JSON with this structure:
{
  "is_invoice": true,
  "confidence": 0.0,
  "products": [
    {
      "code": "string or null",
      "description": "string or null",
      "quantity": 0,
      "price": 0,
      "total": 0
    }
  ],
  "date": "string or null",
  "total": 0
}

confidence must be a number from 0 to 1.
"""


class GeminiInvoiceProvider(AIInvoiceProvider):
    name = "google_genai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError("Falta configurar GOOGLE_API_KEY o API_KEY en el entorno/.env")
        self.model_name = settings.google_model
        self.api_key = settings.google_api_key

    def extract_invoice(self, image_url: str) -> ProviderInvoiceResult:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=0,
            api_key=self.api_key,
            response_mime_type="application/json",
        )

        started_at = time.perf_counter()
        response = model.invoke(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=[
                        {"type": "text", "text": USER_PROMPT},
                        {"type": "image_url", "image_url": image_url},
                    ]
                ),
            ]
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        content = response.content
        parsed = _parse_json_content(content)

        return ProviderInvoiceResult(
            provider=self.name,
            model=self.model_name,
            data=InvoiceData.model_validate(parsed),
            usage=_extract_usage(response),
            raw_response=parsed,
            latency_ms=latency_ms,
        )


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        text = "\n".join(_content_part_to_text(part) for part in content)
    else:
        text = str(content)

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _content_part_to_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        return str(part.get("text") or part.get("content") or "")
    return str(part)


def _extract_usage(response: Any) -> ProviderUsage:
    usage_metadata = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage_metadata") or {}

    prompt_tokens = (
        usage_metadata.get("input_tokens")
        or usage_metadata.get("prompt_tokens")
        or token_usage.get("prompt_tokens")
        or token_usage.get("input_tokens")
        or 0
    )
    completion_tokens = (
        usage_metadata.get("output_tokens")
        or usage_metadata.get("completion_tokens")
        or token_usage.get("completion_tokens")
        or token_usage.get("output_tokens")
        or 0
    )
    total_tokens = (
        usage_metadata.get("total_tokens")
        or token_usage.get("total_tokens")
        or int(prompt_tokens)
        + int(completion_tokens)
    )
    return ProviderUsage(
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
        total_tokens=int(total_tokens or 0),
    )
