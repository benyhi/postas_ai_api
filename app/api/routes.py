from fastapi import APIRouter, Depends

from app.core.security import RequestContext, verify_request
from app.schemas import DocumentExtractionRequest, DocumentExtractionResponse
from app.services.document_extractions import DocumentExtractionService


router = APIRouter()


def get_document_extraction_service() -> DocumentExtractionService:
    return DocumentExtractionService()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/document-extractions/process", response_model=DocumentExtractionResponse)
def process_document_extraction(
    payload: DocumentExtractionRequest,
    context: RequestContext = Depends(verify_request),
    service: DocumentExtractionService = Depends(get_document_extraction_service),
) -> DocumentExtractionResponse:
    return service.process(payload, context)


@router.post("/invoices/extract", response_model=DocumentExtractionResponse)
def extract_invoice(
    payload: DocumentExtractionRequest,
    context: RequestContext = Depends(verify_request),
    service: DocumentExtractionService = Depends(get_document_extraction_service),
) -> DocumentExtractionResponse:
    return service.process(payload, context)
