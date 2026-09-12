import uuid

from pydantic import BaseModel

from aierp.enums import DocumentStatus
from aierp.pipeline.reasons import ReviewReason
from aierp.stage2_extraction.schemas import CanonicalInvoice


class DocumentUploadResult(BaseModel):
    document_id: uuid.UUID
    duplicate: bool
    status: DocumentStatus | None = None


class DocumentSummary(BaseModel):
    document_id: uuid.UUID
    status: DocumentStatus
    reasons: list[ReviewReason]
    canonical_invoice: CanonicalInvoice | None
    original_blob_url: str
