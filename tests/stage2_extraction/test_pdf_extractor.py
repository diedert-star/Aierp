import uuid

import pytest

from aierp.stage2_extraction.pdf_extractor import PdfExtractor


def test_pdf_extractor_declares_identity() -> None:
    extractor = PdfExtractor()
    assert extractor.name == "pdf"
    assert extractor.version


def test_pdf_extractor_raises_not_implemented() -> None:
    extractor = PdfExtractor()
    with pytest.raises(NotImplementedError):
        extractor.extract(b"%PDF-1.4 fake bytes", document_id=uuid.uuid4())
