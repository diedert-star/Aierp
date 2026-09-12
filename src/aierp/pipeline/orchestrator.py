import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aierp.blob_store.protocol import BlobStore
from aierp.enums import DocumentStatus, MatchStrategy
from aierp.pipeline.models import DocumentPipelineState
from aierp.pipeline.reasons import (
    ReviewReason,
    counterparty_unconfirmed_reason,
    extraction_not_supported_reason,
    first_invoice_from_supplier_reason,
    reason_from_validation_result,
)
from aierp.pipeline.repository import upsert_pipeline_state
from aierp.stage1_ingest.models import SourceDocument
from aierp.stage2_extraction.models import CanonicalInvoiceRecord
from aierp.stage2_extraction.pdf_extractor import PdfExtractor
from aierp.stage2_extraction.protocol import Extractor
from aierp.stage2_extraction.repository import persist_canonical_invoice
from aierp.stage2_extraction.schemas import CanonicalInvoice
from aierp.stage2_extraction.ubl_extractor import UblExtractor
from aierp.stage3_validation.checks import BookedInvoice, ValidationContext
from aierp.stage3_validation.repository import persist_validation_run
from aierp.stage3_validation.service import run_all_checks
from aierp.stage3_validation.vies_client import ViesClient
from aierp.stage4_counterparty.models import Counterparty
from aierp.stage4_counterparty.service import resolve_counterparty


def _select_extractor(mime_type: str) -> Extractor:
    if "xml" in mime_type:
        return UblExtractor()
    return PdfExtractor()


def _load_booked_invoices(
    session: Session, tenant_id: str, exclude_document_id: uuid.UUID
) -> list[BookedInvoice]:
    latest_version = (
        select(
            CanonicalInvoiceRecord.document_id,
            func.max(CanonicalInvoiceRecord.version).label("max_version"),
        )
        .group_by(CanonicalInvoiceRecord.document_id)
        .subquery()
    )
    rows = session.execute(
        select(CanonicalInvoiceRecord.data)
        .join(SourceDocument, SourceDocument.id == CanonicalInvoiceRecord.document_id)
        .join(
            latest_version,
            (CanonicalInvoiceRecord.document_id == latest_version.c.document_id)
            & (CanonicalInvoiceRecord.version == latest_version.c.max_version),
        )
        .where(
            SourceDocument.tenant_id == tenant_id,
            CanonicalInvoiceRecord.document_id != exclude_document_id,
        )
    ).scalars()

    booked: list[BookedInvoice] = []
    for data in rows:
        invoice = CanonicalInvoice.model_validate(data)
        booked.append(
            BookedInvoice(
                supplier_vat_number=invoice.supplier.vat_number,
                invoice_number=invoice.invoice_number,
                gross_amount=invoice.totals.gross,
                invoice_date=invoice.invoice_date,
            )
        )
    return booked


def run_pipeline(
    session: Session,
    document_id: uuid.UUID,
    *,
    tenant_id: str,
    tenant_vat_number: str,
    blob_store: BlobStore,
    vies_client: ViesClient,
    today: date | None = None,
) -> DocumentPipelineState:
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise ValueError(f"no source_document with id {document_id}")

    extractor = _select_extractor(document.mime_type)
    raw_bytes = blob_store.get(document.blob_key)

    try:
        canonical_invoice = extractor.extract(raw_bytes, document_id=document_id)
    except NotImplementedError:
        unsupported_reasons = [
            extraction_not_supported_reason(document.channel.value, document.mime_type)
        ]
        return upsert_pipeline_state(
            session,
            document_id=document_id,
            status=DocumentStatus.NEEDS_REVIEW,
            reasons=unsupported_reasons,
            canonical_invoice_id=None,
            counterparty_id=None,
            counterparty_match_strategy=None,
            counterparty_match_confidence=None,
        )

    canonical_record = persist_canonical_invoice(session, canonical_invoice)

    existing_invoices = _load_booked_invoices(session, tenant_id, document_id)
    validation_context = ValidationContext(
        tenant_vat_number=tenant_vat_number,
        vies_client=vies_client,
        existing_invoices=existing_invoices,
        today=today if today is not None else date.today(),
    )
    validation_results = run_all_checks(canonical_invoice, validation_context)
    persist_validation_run(
        session,
        document_id=document_id,
        canonical_invoice_id=canonical_record.id,
        results=validation_results,
    )

    counterparty_match = resolve_counterparty(session, tenant_id, canonical_invoice.supplier)

    reasons: list[ReviewReason] = [reason_from_validation_result(r) for r in validation_results]
    if counterparty_match.strategy == MatchStrategy.NEW:
        reasons.append(first_invoice_from_supplier_reason())
    elif counterparty_match.is_provisional:
        counterparty = session.get(Counterparty, counterparty_match.counterparty_id)
        candidate_name = counterparty.display_name if counterparty is not None else ""
        reasons.append(
            counterparty_unconfirmed_reason(candidate_name, counterparty_match.confidence)
        )

    status = DocumentStatus.CLEAN if not reasons else DocumentStatus.NEEDS_REVIEW

    return upsert_pipeline_state(
        session,
        document_id=document_id,
        status=status,
        reasons=reasons,
        canonical_invoice_id=canonical_record.id,
        counterparty_id=counterparty_match.counterparty_id,
        counterparty_match_strategy=counterparty_match.strategy,
        counterparty_match_confidence=counterparty_match.confidence,
    )
