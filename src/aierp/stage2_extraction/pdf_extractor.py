import uuid

from aierp.stage2_extraction.schemas import CanonicalInvoice


class PdfExtractor:
    """Stage 1 stub. PDF text-layer extraction is not implemented yet — no OCR, no heuristics."""

    name = "pdf"
    version = "0.0.0-unimplemented"

    def extract(self, raw_bytes: bytes, *, document_id: uuid.UUID) -> CanonicalInvoice:
        raise NotImplementedError(
            "PDF extraction is not yet implemented; stage 1 covers UBL/Peppol only"
        )
