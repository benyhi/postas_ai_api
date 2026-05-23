from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.schemas import InvoiceData


@dataclass
class ProviderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ProviderInvoiceResult:
    provider: str
    model: str
    data: InvoiceData
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    raw_response: Any = None
    latency_ms: int | None = None


class AIInvoiceProvider(ABC):
    name: str

    @abstractmethod
    def extract_invoice(self, image_url: str) -> ProviderInvoiceResult:
        raise NotImplementedError
