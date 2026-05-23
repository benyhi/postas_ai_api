from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.core.config import Settings, get_settings
from app.core.security import RequestContext
from app.providers.base import ProviderInvoiceResult, ProviderUsage
from app.providers.registry import get_provider
from app.schemas import (
    DocumentExtractionRequest,
    DocumentExtractionResponse,
    DocumentExtractionStatus,
    DocumentUsageRecord,
    InvoiceData,
)
from app.services.images import FetchedImage, fetch_public_image_as_data_uri


class DocumentExtractionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def process(
        self,
        request: DocumentExtractionRequest,
        context: RequestContext,
    ) -> DocumentExtractionResponse:
        processing_started_at = utc_now()
        provider_attempts = self._provider_attempts(request.provider)
        usage_events: list[dict[str, Any]] = []
        fetched_image: FetchedImage | None = None
        attempts_done = 0
        last_result: ProviderInvoiceResult | None = None
        last_error: str | None = None

        try:
            fetched_image = fetch_public_image_as_data_uri(request.file_url, self.settings)
            provider_image = fetched_image.data_uri
        except Exception as exc:
            attempts_done = 1
            last_error = str(exc)
            return self._build_response(
                request=request,
                context=context,
                status="failed",
                processing_started_at=processing_started_at,
                attempts_done=attempts_done,
                raw_response=request.raw_response,
                extracted_data=request.extracted_data,
                confidence=request.confidence,
                error_message=last_error,
                provider=None,
                model=None,
                fetched_image=None,
                usage_events=usage_events,
            )

        for provider_name in provider_attempts:
            attempts_done += 1
            attempt_started_at = utc_now()
            try:
                provider = get_provider(provider_name)
                result = provider.extract_invoice(provider_image)
                status = self._status_for(result.data)
                usage_events.append(
                    self._usage_event(
                        attempt_number=request.attempts + attempts_done,
                        provider=result.provider,
                        model=result.model,
                        status=status,
                        usage=result.usage,
                        confidence=result.data.confidence,
                        latency_ms=result.latency_ms,
                        error_message=None,
                    )
                )

                last_result = result
                if result.data.confidence >= self.settings.minimum_confidence_threshold:
                    break
            except Exception as exc:
                last_error = str(exc)
                usage_events.append(
                    self._usage_event(
                        attempt_number=request.attempts + attempts_done,
                        provider=provider_name,
                        model=None,
                        status="failed",
                        usage=ProviderUsage(),
                        confidence=None,
                        latency_ms=int((utc_now() - attempt_started_at).total_seconds() * 1000),
                        error_message=last_error,
                    )
                )

        if last_result is None:
            return self._build_response(
                request=request,
                context=context,
                status="failed",
                processing_started_at=processing_started_at,
                attempts_done=attempts_done,
                raw_response=request.raw_response,
                extracted_data=request.extracted_data,
                confidence=request.confidence,
                error_message=last_error or "No se pudo extraer informacion del documento",
                provider=usage_events[-1]["provider"] if usage_events else None,
                model=None,
                fetched_image=fetched_image,
                usage_events=usage_events,
            )

        final_status = self._status_for(last_result.data)
        error_message = None
        if final_status == "failed":
            error_message = "Confidence score por debajo del minimo configurado"

        return self._build_response(
            request=request,
            context=context,
            status=final_status,
            processing_started_at=processing_started_at,
            attempts_done=attempts_done,
            raw_response=last_result.raw_response,
            extracted_data=last_result.data.model_dump(mode="json"),
            confidence=round(last_result.data.confidence, 4),
            error_message=error_message,
            provider=last_result.provider,
            model=last_result.model,
            fetched_image=fetched_image,
            usage_events=usage_events,
        )

    def _provider_attempts(self, request_provider: str | None) -> list[str]:
        first_provider = (request_provider or self.settings.ai_provider).strip()
        providers = [first_provider]
        fallback = self.settings.fallback_ai_provider
        if fallback and fallback not in providers:
            providers.append(fallback)
        return providers[: self.settings.max_ai_attempts]

    def _status_for(self, data: InvoiceData) -> DocumentExtractionStatus:
        if not data.is_invoice:
            return "needs_review"
        if data.confidence >= self.settings.accepted_confidence_threshold:
            return "completed"
        if data.confidence >= self.settings.minimum_confidence_threshold:
            return "needs_review"
        return "failed"

    def _build_response(
        self,
        request: DocumentExtractionRequest,
        context: RequestContext,
        status: DocumentExtractionStatus,
        processing_started_at: datetime,
        attempts_done: int,
        raw_response: Any,
        extracted_data: dict[str, Any] | None,
        confidence: float | None,
        error_message: str | None,
        provider: str | None,
        model: str | None,
        fetched_image: FetchedImage | None,
        usage_events: list[dict[str, Any]],
    ) -> DocumentExtractionResponse:
        completed_at = utc_now()
        total_attempts = request.attempts if request.attempts > 0 else attempts_done
        usage = self._usage_record(
            request=request,
            context=context,
            status=status,
            provider=provider,
            model=model,
            confidence=confidence,
            attempts=total_attempts,
            error_message=error_message,
            created_at=completed_at,
            fetched_image=fetched_image,
            usage_events=usage_events,
        )

        return DocumentExtractionResponse(
            uuid=request.uuid,
            tenant_id=request.tenant_id,
            file_url=request.file_url,
            status=status,
            raw_response=raw_response,
            extracted_data=extracted_data,
            confidence=confidence,
            attempts=total_attempts,
            error_message=error_message,
            created_at=request.created_at,
            updated_at=completed_at,
            processing_started_at=processing_started_at,
            completed_at=completed_at,
            confirmed_at=request.confirmed_at,
            usage=usage,
        )

    def _usage_event(
        self,
        attempt_number: int,
        provider: str,
        model: str | None,
        status: DocumentExtractionStatus,
        usage: ProviderUsage,
        confidence: float | None,
        latency_ms: int | None,
        error_message: str | None,
    ) -> dict[str, Any]:
        return {
            "attempt": attempt_number,
            "provider": provider,
            "model": model,
            "status": status,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "estimated_cost_usd": float(self._estimated_cost(usage)),
            "confidence": confidence,
            "latency_ms": latency_ms,
            "error_message": error_message,
        }

    def _usage_record(
        self,
        request: DocumentExtractionRequest,
        context: RequestContext,
        status: DocumentExtractionStatus,
        provider: str | None,
        model: str | None,
        confidence: float | None,
        attempts: int,
        error_message: str | None,
        created_at: datetime,
        fetched_image: FetchedImage | None,
        usage_events: list[dict[str, Any]],
    ) -> DocumentUsageRecord:
        extra: dict[str, Any] = {
            "authenticated": context.authenticated,
            "provider_attempts": usage_events,
        }
        if request.source_request_id:
            extra["source_request_id"] = request.source_request_id
        if request.metadata:
            extra["request_metadata"] = request.metadata
        if fetched_image is not None:
            extra["image"] = {
                "content_type": fetched_image.content_type,
                "size_bytes": fetched_image.size_bytes,
            }

        return DocumentUsageRecord(
            tenant_id=request.tenant_id,
            document_extraction_uuid=request.uuid,
            source=context.source,
            provider=provider,
            model=model,
            status=status,
            prompt_tokens=sum(int(event["prompt_tokens"] or 0) for event in usage_events),
            completion_tokens=sum(int(event["completion_tokens"] or 0) for event in usage_events),
            total_tokens=sum(int(event["total_tokens"] or 0) for event in usage_events),
            estimated_cost_usd=sum(float(event["estimated_cost_usd"] or 0.0) for event in usage_events),
            confidence=confidence,
            latency_ms=sum(
                int(event["latency_ms"] or 0)
                for event in usage_events
                if event.get("latency_ms") is not None
            )
            or None,
            attempts=attempts,
            error_message=error_message,
            created_at=created_at,
            extra=extra,
        )

    def _estimated_cost(self, usage: ProviderUsage) -> Decimal:
        input_cost = (usage.prompt_tokens / 1_000_000) * self.settings.input_token_cost_per_million
        output_cost = (usage.completion_tokens / 1_000_000) * self.settings.output_token_cost_per_million
        return Decimal(str(round(input_cost + output_cost, 6)))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
