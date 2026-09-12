import uuid
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from aierp.blob_store.protocol import BlobStore
from aierp.enums import AliasType, Channel, CounterpartyStatus, DocumentStatus
from aierp.pipeline.orchestrator import run_pipeline
from aierp.pipeline.reasons import PipelineReasonCode
from aierp.stage1_ingest.service import ingest_document
from aierp.stage3_validation.codes import ValidationCode
from aierp.stage3_validation.vies_client import ViesClient
from aierp.stage4_counterparty.models import Counterparty, CounterpartyAlias
from aierp.stage4_counterparty.normalize import normalize_vat_number

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ubl"
TENANT_ID = "tenant-a"
TENANT_VAT = "BE0999999999"
PIPELINE_TODAY = date(2024, 3, 20)


class _AlwaysValidViesClient:
    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        return True


_VIES_CLIENT: ViesClient = _AlwaysValidViesClient()


def _ingest(
    db_session: Session,
    blob_store: BlobStore,
    filename: str,
    *,
    mime_type: str = "application/xml",
) -> uuid.UUID:
    result = ingest_document(
        db_session,
        blob_store,
        tenant_id=TENANT_ID,
        channel=Channel.PEPPOL,
        raw_bytes=(FIXTURES / filename).read_bytes(),
        original_filename=filename,
        mime_type=mime_type,
    )
    return result.document_id


def _run(db_session: Session, blob_store: BlobStore, document_id: uuid.UUID):  # type: ignore[no-untyped-def]
    return run_pipeline(
        db_session,
        document_id,
        tenant_id=TENANT_ID,
        tenant_vat_number=TENANT_VAT,
        blob_store=blob_store,
        vies_client=_VIES_CLIENT,
        today=PIPELINE_TODAY,
    )


def _pre_confirm_supplier(db_session: Session, vat_number: str, display_name: str) -> None:
    counterparty = Counterparty(
        tenant_id=TENANT_ID, display_name=display_name, status=CounterpartyStatus.CONFIRMED
    )
    db_session.add(counterparty)
    db_session.flush()
    db_session.add(
        CounterpartyAlias(
            counterparty_id=counterparty.id,
            tenant_id=TENANT_ID,
            alias_type=AliasType.VAT_NUMBER,
            raw_value=vat_number,
            normalized_value=normalize_vat_number(vat_number),
        )
    )
    db_session.flush()


def test_clean_invoice_from_confirmed_supplier_is_clean(
    db_session: Session, blob_store: BlobStore
) -> None:
    _pre_confirm_supplier(db_session, "BE0123456749", "Acme Leverancier BV")

    document_id = _ingest(db_session, blob_store, "valid_be_domestic_21.xml")
    state = _run(db_session, blob_store, document_id)

    assert state.status == DocumentStatus.CLEAN
    assert state.reasons == []


def test_unknown_supplier_needs_review_with_first_invoice_reason(
    db_session: Session, blob_store: BlobStore
) -> None:
    document_id = _ingest(db_session, blob_store, "unknown_supplier.xml")

    state = _run(db_session, blob_store, document_id)

    assert state.status == DocumentStatus.NEEDS_REVIEW
    codes = {reason["code"] for reason in state.reasons}
    assert PipelineReasonCode.FIRST_INVOICE_FROM_SUPPLIER.value in codes


def test_bad_arithmetic_needs_review_with_arithmetic_reason(
    db_session: Session, blob_store: BlobStore
) -> None:
    _pre_confirm_supplier(db_session, "BE0345678912", "Rekenfout Diensten BV")
    document_id = _ingest(db_session, blob_store, "invalid_vat_arithmetic.xml")

    state = _run(db_session, blob_store, document_id)

    assert state.status == DocumentStatus.NEEDS_REVIEW
    codes = {reason["code"] for reason in state.reasons}
    assert ValidationCode.VAT_RATE_ARITHMETIC_MISMATCH.value in codes


def test_malformed_vat_needs_review_with_structural_reason(
    db_session: Session, blob_store: BlobStore
) -> None:
    document_id = _ingest(db_session, blob_store, "malformed_supplier_vat.xml")

    state = _run(db_session, blob_store, document_id)

    assert state.status == DocumentStatus.NEEDS_REVIEW
    codes = {reason["code"] for reason in state.reasons}
    assert ValidationCode.SUPPLIER_VAT_STRUCTURALLY_INVALID.value in codes


def test_intracommunity_reverse_charge_invoice_is_clean_when_confirmed(
    db_session: Session, blob_store: BlobStore
) -> None:
    _pre_confirm_supplier(db_session, "NL123456789B01", "Intra Trade B.V.")
    document_id = _ingest(db_session, blob_store, "valid_intracommunity_reverse_charge.xml")

    state = _run(db_session, blob_store, document_id)

    assert state.status == DocumentStatus.CLEAN


def test_near_duplicate_detected_against_previously_booked_invoice(
    db_session: Session, blob_store: BlobStore
) -> None:
    _pre_confirm_supplier(db_session, "BE0123456749", "Acme Leverancier BV")

    first_document_id = _ingest(db_session, blob_store, "valid_be_domestic_21.xml")
    first_state = _run(db_session, blob_store, first_document_id)
    assert first_state.status == DocumentStatus.CLEAN

    second_document_id = _ingest(
        db_session, blob_store, "near_duplicate_of_valid_be_domestic_21.xml"
    )
    second_state = _run(db_session, blob_store, second_document_id)

    assert second_state.status == DocumentStatus.NEEDS_REVIEW
    codes = {reason["code"] for reason in second_state.reasons}
    assert ValidationCode.NEAR_DUPLICATE_INVOICE.value in codes


def test_exact_duplicate_supplier_and_invoice_number_flagged(
    db_session: Session, blob_store: BlobStore
) -> None:
    _pre_confirm_supplier(db_session, "BE0123456749", "Acme Leverancier BV")

    original_bytes = (FIXTURES / "valid_be_domestic_21.xml").read_bytes()
    # Same supplier + invoice number, but not byte-identical — a genuine resubmission
    # (e.g. re-scanned), not a stage-1 sha256 duplicate.
    resent_bytes = original_bytes.replace(b"<Invoice ", b"<!--resubmitted--><Invoice ", 1)

    first_result = ingest_document(
        db_session,
        blob_store,
        tenant_id=TENANT_ID,
        channel=Channel.PEPPOL,
        raw_bytes=original_bytes,
        original_filename="valid_be_domestic_21.xml",
        mime_type="application/xml",
    )
    _run(db_session, blob_store, first_result.document_id)

    second_result = ingest_document(
        db_session,
        blob_store,
        tenant_id=TENANT_ID,
        channel=Channel.PEPPOL,
        raw_bytes=resent_bytes,
        original_filename="valid_be_domestic_21_resubmitted.xml",
        mime_type="application/xml",
    )
    assert second_result.duplicate is False

    second_state = _run(db_session, blob_store, second_result.document_id)

    assert second_state.status == DocumentStatus.NEEDS_REVIEW
    codes = {reason["code"] for reason in second_state.reasons}
    assert ValidationCode.DUPLICATE_INVOICE.value in codes


def test_extraction_not_supported_for_non_xml_channel(
    db_session: Session, blob_store: BlobStore
) -> None:
    result = ingest_document(
        db_session,
        blob_store,
        tenant_id=TENANT_ID,
        channel=Channel.UPLOAD,
        raw_bytes=b"%PDF-1.4 not really a pdf",
        original_filename="scan.pdf",
        mime_type="application/pdf",
    )

    state = _run(db_session, blob_store, result.document_id)

    assert state.status == DocumentStatus.NEEDS_REVIEW
    assert state.canonical_invoice_id is None
    codes = {reason["code"] for reason in state.reasons}
    assert PipelineReasonCode.EXTRACTION_NOT_SUPPORTED.value in codes
