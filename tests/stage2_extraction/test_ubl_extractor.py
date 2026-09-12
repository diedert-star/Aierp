import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from aierp.stage2_extraction.ubl_extractor import UblExtractionError, UblExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ubl"


def _extract(filename: str):
    extractor = UblExtractor()
    raw_bytes = (FIXTURES / filename).read_bytes()
    return extractor.extract(raw_bytes, document_id=uuid.uuid4())


def test_extractor_identity() -> None:
    extractor = UblExtractor()
    assert extractor.name == "ubl"
    assert extractor.version


def test_domestic_21_percent_invoice() -> None:
    invoice = _extract("valid_be_domestic_21.xml")

    assert invoice.invoice_number == "2024-0001"
    assert invoice.invoice_date.isoformat() == "2024-03-15"
    assert invoice.due_date is not None and invoice.due_date.isoformat() == "2024-04-14"
    assert invoice.currency == "EUR"

    assert invoice.supplier.name == "Acme Leverancier BV"
    assert invoice.supplier.vat_number == "BE0123456749"
    assert invoice.supplier.country_code == "BE"
    assert invoice.supplier.iban == "BE68539007547034"

    assert invoice.buyer.vat_number == "BE0999999999"

    assert len(invoice.lines) == 1
    line = invoice.lines[0]
    assert line.net_amount == Decimal("320.00")
    assert line.vat_rate == Decimal("0.21")
    assert line.vat_amount == Decimal("67.20")

    assert len(invoice.vat_breakdown) == 1
    assert invoice.vat_breakdown[0].rate == Decimal("0.21")
    assert invoice.vat_breakdown[0].taxable_base == Decimal("320.00")
    assert invoice.vat_breakdown[0].vat_amount == Decimal("67.20")

    assert invoice.totals.net == Decimal("320.00")
    assert invoice.totals.vat == Decimal("67.20")
    assert invoice.totals.gross == Decimal("387.20")
    assert invoice.payment_reference == "+++123/4567/89012+++"

    assert invoice.extractor.name == "ubl"
    assert invoice.extraction_confidence["invoice_number"] == 1.0
    assert invoice.extraction_confidence["supplier.vat_number"] == 1.0


def test_mixed_rate_invoice_has_two_lines_and_two_breakdown_entries() -> None:
    invoice = _extract("valid_mixed_21_6.xml")

    assert len(invoice.lines) == 2
    rates = {line.vat_rate for line in invoice.lines}
    assert rates == {Decimal("0.21"), Decimal("0.06")}

    assert len(invoice.vat_breakdown) == 2
    assert invoice.totals.vat == Decimal("45.60")
    assert invoice.totals.net == Decimal("260.00")
    assert invoice.totals.gross == Decimal("305.60")


def test_intracommunity_reverse_charge_invoice_has_exemption_code() -> None:
    invoice = _extract("valid_intracommunity_reverse_charge.xml")

    assert invoice.supplier.country_code == "NL"
    assert invoice.supplier.vat_number == "NL123456789B01"

    assert invoice.vat_breakdown[0].rate == Decimal("0")
    assert invoice.vat_breakdown[0].exemption_reason_code == "VATEX-EU-AE"
    assert invoice.totals.vat == Decimal("0.00")
    assert invoice.totals.gross == invoice.totals.net


def test_invoice_with_bad_arithmetic_still_extracts_verbatim() -> None:
    # Stage 2 maps fields as declared in the source; it does not validate arithmetic.
    invoice = _extract("invalid_vat_arithmetic.xml")

    assert invoice.totals.vat == Decimal("71.40")
    line = invoice.lines[0]
    assert line.net_amount * Decimal("0.21") != invoice.vat_breakdown[0].vat_amount


def test_malformed_supplier_vat_still_extracts_verbatim() -> None:
    # Structural VAT validity is a stage-3 concern; extraction just maps the raw value.
    invoice = _extract("malformed_supplier_vat.xml")
    assert invoice.supplier.vat_number == "BE12"


def test_extract_raises_on_non_xml_input() -> None:
    extractor = UblExtractor()
    with pytest.raises(UblExtractionError):
        extractor.extract(b"not xml at all", document_id=uuid.uuid4())


def test_extract_raises_when_mandatory_invoice_id_missing() -> None:
    extractor = UblExtractor()
    minimal_invoice_without_id = b"""<?xml version="1.0"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:IssueDate>2024-01-01</cbc:IssueDate>
</Invoice>"""
    with pytest.raises(UblExtractionError):
        extractor.extract(minimal_invoice_without_id, document_id=uuid.uuid4())
