from app.providers.base import AIInvoiceProvider
from app.providers.gemini import GeminiInvoiceProvider
from app.providers.mock import MockInvoiceProvider


PROVIDERS: dict[str, type[AIInvoiceProvider]] = {
    "google_genai": GeminiInvoiceProvider,
    "gemini": GeminiInvoiceProvider,
    "mock": MockInvoiceProvider,
}


def get_provider(provider_name: str) -> AIInvoiceProvider:
    normalized_name = provider_name.strip().lower()
    provider_class = PROVIDERS.get(normalized_name)
    if provider_class is None:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Proveedor IA no soportado: {provider_name}. Disponibles: {available}")
    return provider_class()
