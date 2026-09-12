from sqlalchemy.orm import Session

from aierp.blob_store.protocol import BlobStore
from aierp.enums import Channel
from aierp.stage1_ingest.service import blob_key_for, ingest_document


def test_blob_key_is_content_addressed_and_shards_by_prefix() -> None:
    key = blob_key_for("tenant-a", "abcdef0123456789")
    assert key == "tenant-a/ab/cd/abcdef0123456789"


def test_ingest_document_stores_bytes_and_creates_row(
    db_session: Session, blob_store: BlobStore
) -> None:
    result = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-a",
        channel=Channel.UPLOAD,
        raw_bytes=b"invoice bytes",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
    )

    assert result.duplicate is False

    from aierp.stage1_ingest.models import SourceDocument

    row = db_session.get(SourceDocument, result.document_id)
    assert row is not None
    assert row.tenant_id == "tenant-a"
    assert row.byte_size == len(b"invoice bytes")
    assert row.mime_type == "application/pdf"
    assert row.channel == Channel.UPLOAD
    assert blob_store.get(row.blob_key) == b"invoice bytes"


def test_ingest_same_bytes_twice_for_same_tenant_returns_duplicate(
    db_session: Session, blob_store: BlobStore
) -> None:
    first = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-a",
        channel=Channel.UPLOAD,
        raw_bytes=b"same bytes",
        original_filename="a.pdf",
        mime_type="application/pdf",
    )
    second = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-a",
        channel=Channel.EMAIL,
        raw_bytes=b"same bytes",
        original_filename="a-resent.pdf",
        mime_type="application/pdf",
    )

    assert second.duplicate is True
    assert second.document_id == first.document_id


def test_ingest_same_bytes_for_different_tenants_are_not_duplicates(
    db_session: Session, blob_store: BlobStore
) -> None:
    first = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-a",
        channel=Channel.UPLOAD,
        raw_bytes=b"shared bytes",
        original_filename="a.pdf",
        mime_type="application/pdf",
    )
    second = ingest_document(
        db_session,
        blob_store,
        tenant_id="tenant-b",
        channel=Channel.UPLOAD,
        raw_bytes=b"shared bytes",
        original_filename="a.pdf",
        mime_type="application/pdf",
    )

    assert second.duplicate is False
    assert second.document_id != first.document_id
