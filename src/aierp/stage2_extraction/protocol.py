import uuid
from typing import Protocol

from aierp.stage2_extraction.schemas import CanonicalInvoice


class Extractor(Protocol):
    name: str
    version: str

    def extract(self, raw_bytes: bytes, *, document_id: uuid.UUID) -> CanonicalInvoice: ...
