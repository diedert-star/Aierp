from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from aierp.api.deps import get_blob_store, get_db_session, get_tenant_id
from aierp.blob_store.protocol import BlobStore
from aierp.enums import Channel
from aierp.stage1_ingest.schemas import IngestResult
from aierp.stage1_ingest.service import ingest_document

router = APIRouter()


@router.post("/documents", response_model=IngestResult)
async def upload_document(
    file: UploadFile = File(...),
    channel: Channel = Form(...),
    tenant_id: str = Depends(get_tenant_id),
    session: Session = Depends(get_db_session),
    blob_store: BlobStore = Depends(get_blob_store),
) -> IngestResult:
    raw_bytes = await file.read()
    return ingest_document(
        session,
        blob_store,
        tenant_id=tenant_id,
        channel=channel,
        raw_bytes=raw_bytes,
        original_filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
    )
