import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from aierp.blob_store.protocol import BlobStore
from aierp.enums import Channel
from aierp.stage1_ingest.models import SourceDocument
from aierp.stage1_ingest.schemas import IngestResult


def blob_key_for(tenant_id: str, sha256: str) -> str:
    return f"{tenant_id}/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def ingest_document(
    session: Session,
    blob_store: BlobStore,
    *,
    tenant_id: str,
    channel: Channel,
    raw_bytes: bytes,
    original_filename: str | None,
    mime_type: str,
) -> IngestResult:
    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    existing = session.execute(
        select(SourceDocument).where(
            SourceDocument.tenant_id == tenant_id,
            SourceDocument.sha256 == sha256,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return IngestResult(document_id=existing.id, duplicate=True)

    key = blob_key_for(tenant_id, sha256)
    blob_store.put(key, raw_bytes)

    document = SourceDocument(
        tenant_id=tenant_id,
        sha256=sha256,
        blob_key=key,
        channel=channel,
        original_filename=original_filename,
        mime_type=mime_type,
        byte_size=len(raw_bytes),
        received_at=datetime.now(UTC),
    )
    session.add(document)
    session.flush()

    return IngestResult(document_id=document.id, duplicate=False)
