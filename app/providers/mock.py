import time

from app.providers.base import AIInvoiceProvider, ProviderInvoiceResult, ProviderUsage
from app.schemas import InvoiceData


class MockInvoiceProvider(AIInvoiceProvider):
    name = "mock"
    model_name = "mock-invoice-extractor"

    def extract_invoice(self, image_url: str) -> ProviderInvoiceResult:
        started_at = time.perf_counter()
        data = InvoiceData.model_validate(
            {
                "is_invoice": True,
                "confidence": 0.9,
                "products": [
                    {
                        "code": "MOCK-001",
                        "description": "Producto de prueba",
                        "quantity": 1,
                        "price": 100,
                        "total": 100,
                    }
                ],
                "date": None,
                "total": 100,
            }
        )
        return ProviderInvoiceResult(
            provider=self.name,
            model=self.model_name,
            data=data,
            usage=ProviderUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            raw_response=data.model_dump(mode="json"),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
        )
