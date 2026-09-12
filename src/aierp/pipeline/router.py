import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from aierp.api.deps import (
    get_blob_store,
    get_db_session,
    get_tenant_id,
    get_tenant_vat_number,
    get_vies_client,
)
from aierp.blob_store.protocol import BlobStore
from aierp.enums import Channel, DocumentStatus
from aierp.pipeline.models import DocumentPipelineState
from aierp.pipeline.orchestrator import run_pipeline
from aierp.pipeline.reasons import ReviewReason
from aierp.pipeline.repository import list_pipeline_states
from aierp.pipeline.schemas import DocumentSummary, DocumentUploadResult
from aierp.stage1_ingest.models import SourceDocument
from aierp.stage1_ingest.service import ingest_document
from aierp.stage2_extraction.models import CanonicalInvoiceRecord
from aierp.stage2_extraction.repository import load_canonical_invoice
from aierp.stage3_validation.vies_client import ViesClient

router = APIRouter()


@router.post("/documents", response_model=DocumentUploadResult)
async def upload_document(
    file: UploadFile = File(...),
    channel: Channel = Form(...),
    tenant_id: str = Depends(get_tenant_id),
    tenant_vat_number: str = Depends(get_tenant_vat_number),
    session: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
    vies_client: ViesClient = Depends(get_vies_client),
) -> DocumentUploadResult:
    raw_bytes = await file.read()
    ingest_result = ingest_document(
        session,
        blob_store,
        tenant_id=tenant_id,
        channel=channel,
        raw_bytes=raw_bytes,
        original_filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
    )

    if ingest_result.duplicate:
        existing_state = session.get(DocumentPipelineState, ingest_result.document_id)
        status = existing_state.status if existing_state is not None else None
        return DocumentUploadResult(
            document_id=ingest_result.document_id, duplicate=True, status=status
        )

    state = run_pipeline(
        session,
        ingest_result.document_id,
        tenant_id=tenant_id,
        tenant_vat_number=tenant_vat_number,
        blob_store=blob_store,
        vies_client=vies_client,
    )
    return DocumentUploadResult(
        document_id=ingest_result.document_id, duplicate=False, status=state.status
    )


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    status: DocumentStatus | None = None,
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_db_session),
) -> list[DocumentSummary]:
    states = list_pipeline_states(session, tenant_id=tenant_id, status=status)

    summaries: list[DocumentSummary] = []
    for state in states:
        canonical_invoice = None
        if state.canonical_invoice_id is not None:
            record = session.get(CanonicalInvoiceRecord, state.canonical_invoice_id)
            if record is not None:
                canonical_invoice = load_canonical_invoice(record)

        summaries.append(
            DocumentSummary(
                document_id=state.document_id,
                status=state.status,
                reasons=[ReviewReason.model_validate(reason) for reason in state.reasons],
                canonical_invoice=canonical_invoice,
                original_blob_url=f"/documents/{state.document_id}/original",
            )
        )
    return summaries


@router.get("/documents/{document_id}/original")
def get_original_document(
    document_id: uuid.UUID,
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> Response:
    document = session.get(SourceDocument, document_id)
    if document is None or document.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="document not found")

    raw_bytes = blob_store.get(document.blob_key)
    return Response(content=raw_bytes, media_type=document.mime_type)
