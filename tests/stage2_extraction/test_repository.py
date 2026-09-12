import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from aierp.blob_store.protocol import BlobStore
from aierp.enums import Channel
from aierp.stage1_ingest.service import ingest_document
from aierp.stage2_extraction.repository import load_canonical_invoice, persist_canonical_invoice
from aierp.stage2_extraction.schemas import (
    CanonicalInvoice,
    ExtractorInfo,
    Party,
    Totals,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ubl"


def _make_canonical_invoice(document_id: uuid.UUID, invoice_number: str) -> CanonicalInvoice:
    return CanonicalInvoice(
        document_id=document_id,
        supplier=Party(name="Acme Leverancier BV", vat_number="BE0123456749"),
        buyer=Party(name="Klant NV", vat_number="BE0999999999"),
        invoice_number=invoice_number,
        invoice_date=datetime.now(UTC).date(),
        due_date=None,
        currency="EUR",
        lines=[],
        vat_breakdown=[],
        totals=Totals(
            net=Decimal("320.00"),
            vat=Decimal("67.20"),
            gross=Decimal("387.20"),
            prepaid=Decimal("0.00"),
            payable=Decimal("387.20"),
        ),
        payment_reference=None,
        extraction_confidence={"invoice_number": 1.0},
        extractor=ExtractorInfo(name="ubl", version="1.0.0"),
    )


def _ingested_document_id(db_session: Session, blob_store: BlobStore) -> uuid.UUID:
    result = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-a",
        channel=Channel.PEPPOL,
        raw_bytes=(FIXTURES / "valid_be_domestic_21.xml").read_bytes(),
        original_filename="valid_be_domestic_21.xml",
        mime_type="application/xml",
    )
    return result.document_id


def test_persist_creates_version_one(db_session: Session, blob_store: BlobStore) -> None:
    document_id = _ingested_document_id(db_session, blob_store)
    canonical_invoice = _make_canonical_invoice(document_id, "2024-0001")

    record = persist_canonical_invoice(db_session, canonical_invoice)

    assert record.version == 1
    assert record.extractor_name == "ubl"
    reloaded = load_canonical_invoice(record)
    assert reloaded.invoice_number == "2024-0001"
    assert reloaded.totals.vat == Decimal("67.20")


def test_re_extraction_creates_new_version_never_overwrites(
    db_session: Session, blob_store: BlobStore
) -> None:
    document_id = _ingested_document_id(db_session, blob_store)

    first = persist_canonical_invoice(db_session, _make_canonical_invoice(document_id, "2024-0001"))
    second = persist_canonical_invoice(
        db_session, _make_canonical_invoice(document_id, "2024-0001-corrected")
    )

    assert first.version == 1
    assert second.version == 2
    assert first.id != second.id

    reloaded_first = load_canonical_invoice(first)
    assert reloaded_first.invoice_number == "2024-0001"
