import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aierp.stage2_extraction.models import CanonicalInvoiceRecord
from aierp.stage2_extraction.schemas import CanonicalInvoice


def persist_canonical_invoice(
    session: Session, canonical_invoice: CanonicalInvoice
) -> CanonicalInvoiceRecord:
    """Insert a new version of the canonical record for this document. Never updates in place."""
    current_max_version = session.execute(
        select(func.max(CanonicalInvoiceRecord.version)).where(
            CanonicalInvoiceRecord.document_id == canonical_invoice.document_id
        )
    ).scalar_one()
    next_version = (current_max_version or 0) + 1

    record = CanonicalInvoiceRecord(
        document_id=canonical_invoice.document_id,
        version=next_version,
        extractor_name=canonical_invoice.extractor.name,
        extractor_version=canonical_invoice.extractor.version,
        data=json.loads(canonical_invoice.model_dump_json()),
    )
    session.add(record)
    session.flush()
    return record


def load_canonical_invoice(record: CanonicalInvoiceRecord) -> CanonicalInvoice:
    return CanonicalInvoice.model_validate(record.data)
