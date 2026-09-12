import uuid

from pydantic import BaseModel


class IngestResult(BaseModel):
    document_id: uuid.UUID
    duplicate: bool
