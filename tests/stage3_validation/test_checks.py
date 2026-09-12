from datetime import date, timedelta
from decimal import Decimal

from aierp.stage3_validation.checks import (
    BookedInvoice,
    check_buyer_vat,
    check_currency,
    check_duplicate,
    check_invoice_date,
    check_line_net_total,
    check_near_duplicate,
    check_supplier_iban,
    check_supplier_vat_structural,
    check_supplier_vat_vies,
    check_totals_gross,
    check_vat_breakdown_total,
    check_vat_rate_arithmetic,
)
from aierp.stage3_validation.codes import ValidationCode
from tests.stage3_validation.factories import (
    DEFAULT_INVOICE_DATE,
    DEFAULT_SUPPLIER_VAT,
    DEFAULT_TENANT_VAT,
    make_invoice,
)

# --- VAT rate arithmetic -----------------------------------------------------------------


def test_vat_rate_arithmetic_passes_when_consistent() -> None:
    invoice = make_invoice(net=Decimal("100.00"), vat=Decimal("21.00"), rate=Decimal("0.21"))
    assert check_vat_rate_arithmetic(invoice) == []


def test_vat_rate_arithmetic_fails_when_inconsistent() -> None:
    invoice = make_invoice(net=Decimal("100.00"), vat=Decimal("30.00"), rate=Decimal("0.21"))
    results = check_vat_rate_arithmetic(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.VAT_RATE_ARITHMETIC_MISMATCH


# --- VAT breakdown total -----------------------------------------------------------------


def test_vat_breakdown_total_passes_when_it_matches_totals_vat() -> None:
    invoice = make_invoice(vat=Decimal("21.00"))
    assert check_vat_breakdown_total(invoice) == []


def test_vat_breakdown_total_fails_when_it_does_not_match_totals_vat() -> None:
    invoice = make_invoice(vat=Decimal("21.00"))
    invoice.totals.vat = Decimal("25.00")
    results = check_vat_breakdown_total(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.VAT_BREAKDOWN_TOTAL_MISMATCH


# --- line net total -----------------------------------------------------------------------


def test_line_net_total_passes_when_it_matches_totals_net() -> None:
    invoice = make_invoice(net=Decimal("100.00"))
    assert check_line_net_total(invoice) == []


def test_line_net_total_fails_when_it_does_not_match_totals_net() -> None:
    invoice = make_invoice(net=Decimal("100.00"))
    invoice.totals.net = Decimal("150.00")
    results = check_line_net_total(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.LINE_NET_TOTAL_MISMATCH


# --- gross totals ---------------------------------------------------------------------------


def test_totals_gross_passes_when_net_plus_vat_equals_gross() -> None:
    invoice = make_invoice(net=Decimal("100.00"), vat=Decimal("21.00"), gross=Decimal("121.00"))
    assert check_totals_gross(invoice) == []


def test_totals_gross_fails_when_net_plus_vat_does_not_equal_gross() -> None:
    invoice = make_invoice(net=Decimal("100.00"), vat=Decimal("21.00"), gross=Decimal("200.00"))
    results = check_totals_gross(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.TOTALS_GROSS_MISMATCH


# --- supplier VAT structural ----------------------------------------------------------------


def test_supplier_vat_structural_passes_for_valid_format() -> None:
    invoice = make_invoice(supplier_vat="BE0123456749")
    assert check_supplier_vat_structural(invoice) == []


def test_supplier_vat_structural_fails_for_malformed_number() -> None:
    invoice = make_invoice(supplier_vat="BE12")
    results = check_supplier_vat_structural(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.SUPPLIER_VAT_STRUCTURALLY_INVALID


# --- supplier VAT VIES -----------------------------------------------------------------------


class _StubViesClient:
    def __init__(self, result: bool | None) -> None:
        self._result = result

    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        return self._result


def test_supplier_vies_passes_when_vies_confirms_valid() -> None:
    invoice = make_invoice(supplier_vat=DEFAULT_SUPPLIER_VAT)
    assert check_supplier_vat_vies(invoice, _StubViesClient(True)) == []


def test_supplier_vies_fails_when_vies_confirms_invalid() -> None:
    invoice = make_invoice(supplier_vat=DEFAULT_SUPPLIER_VAT)
    results = check_supplier_vat_vies(invoice, _StubViesClient(False))
    assert len(results) == 1
    assert results[0].code == ValidationCode.SUPPLIER_VAT_VIES_INVALID


def test_supplier_vies_warns_but_does_not_block_on_outage() -> None:
    invoice = make_invoice(supplier_vat=DEFAULT_SUPPLIER_VAT)
    results = check_supplier_vat_vies(invoice, _StubViesClient(None))
    assert len(results) == 1
    assert results[0].code == ValidationCode.VIES_UNAVAILABLE
    assert results[0].severity.value == "warning"


# --- supplier IBAN ----------------------------------------------------------------------------


def test_supplier_iban_passes_when_checksum_valid() -> None:
    invoice = make_invoice(supplier_iban="BE68539007547034")
    assert check_supplier_iban(invoice) == []


def test_supplier_iban_fails_when_checksum_invalid() -> None:
    invoice = make_invoice(supplier_iban="BE00000000000000")
    results = check_supplier_iban(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.SUPPLIER_IBAN_CHECKSUM_INVALID


def test_supplier_iban_skipped_when_absent() -> None:
    invoice = make_invoice(supplier_iban=None)
    assert check_supplier_iban(invoice) == []


# --- invoice date -------------------------------------------------------------------------------


def test_invoice_date_passes_when_recent_and_not_in_future() -> None:
    invoice = make_invoice(invoice_date=DEFAULT_INVOICE_DATE)
    results = check_invoice_date(invoice, today=DEFAULT_INVOICE_DATE + timedelta(days=1))
    assert results == []


def test_invoice_date_fails_when_in_future() -> None:
    invoice = make_invoice(invoice_date=date(2030, 1, 1))
    results = check_invoice_date(invoice, today=date(2024, 1, 1))
    assert len(results) == 1
    assert results[0].code == ValidationCode.INVOICE_DATE_IN_FUTURE


def test_invoice_date_warns_when_older_than_24_months() -> None:
    invoice = make_invoice(invoice_date=date(2020, 1, 1))
    results = check_invoice_date(invoice, today=date(2024, 1, 1))
    assert len(results) == 1
    assert results[0].code == ValidationCode.INVOICE_DATE_TOO_OLD
    assert results[0].severity.value == "warning"


# --- buyer VAT ------------------------------------------------------------------------------------


def test_buyer_vat_passes_when_it_matches_tenant() -> None:
    invoice = make_invoice(buyer_vat=DEFAULT_TENANT_VAT)
    assert check_buyer_vat(invoice, DEFAULT_TENANT_VAT) == []


def test_buyer_vat_fails_when_it_does_not_match_tenant() -> None:
    invoice = make_invoice(buyer_vat="BE0111111111")
    results = check_buyer_vat(invoice, DEFAULT_TENANT_VAT)
    assert len(results) == 1
    assert results[0].code == ValidationCode.BUYER_VAT_MISMATCH


# --- currency -------------------------------------------------------------------------------------


def test_currency_passes_for_eur() -> None:
    invoice = make_invoice(currency="EUR")
    assert check_currency(invoice) == []


def test_currency_warns_for_non_eur() -> None:
    invoice = make_invoice(currency="USD")
    results = check_currency(invoice)
    assert len(results) == 1
    assert results[0].code == ValidationCode.CURRENCY_NOT_EUR
    assert results[0].severity.value == "warning"


# --- duplicate detection --------------------------------------------------------------------------


def test_duplicate_passes_when_no_matching_existing_invoice() -> None:
    invoice = make_invoice(invoice_number="2024-0001")
    existing = [
        BookedInvoice(
            supplier_vat_number=DEFAULT_SUPPLIER_VAT,
            invoice_number="2024-9999",
            gross_amount=Decimal("121.00"),
            invoice_date=DEFAULT_INVOICE_DATE,
        )
    ]
    assert check_duplicate(invoice, existing) == []


def test_duplicate_fails_when_same_supplier_and_invoice_number_already_booked() -> None:
    invoice = make_invoice(invoice_number="2024-0001", supplier_vat=DEFAULT_SUPPLIER_VAT)
    existing = [
        BookedInvoice(
            supplier_vat_number=DEFAULT_SUPPLIER_VAT,
            invoice_number="2024-0001",
            gross_amount=Decimal("121.00"),
            invoice_date=DEFAULT_INVOICE_DATE,
        )
    ]
    results = check_duplicate(invoice, existing)
    assert len(results) == 1
    assert results[0].code == ValidationCode.DUPLICATE_INVOICE


# --- near-duplicate detection ---------------------------------------------------------------------


def test_near_duplicate_passes_when_dates_are_far_apart() -> None:
    invoice = make_invoice(
        invoice_number="2024-0002", supplier_vat=DEFAULT_SUPPLIER_VAT, gross=Decimal("121.00")
    )
    existing = [
        BookedInvoice(
            supplier_vat_number=DEFAULT_SUPPLIER_VAT,
            invoice_number="2024-0001",
            gross_amount=Decimal("121.00"),
            invoice_date=DEFAULT_INVOICE_DATE - timedelta(days=30),
        )
    ]
    assert check_near_duplicate(invoice, existing) == []


def test_near_duplicate_warns_when_same_supplier_amount_and_close_date() -> None:
    invoice = make_invoice(
        invoice_number="2024-0002",
        supplier_vat=DEFAULT_SUPPLIER_VAT,
        gross=Decimal("121.00"),
        invoice_date=DEFAULT_INVOICE_DATE + timedelta(days=2),
    )
    existing = [
        BookedInvoice(
            supplier_vat_number=DEFAULT_SUPPLIER_VAT,
            invoice_number="2024-0001",
            gross_amount=Decimal("121.00"),
            invoice_date=DEFAULT_INVOICE_DATE,
        )
    ]
    results = check_near_duplicate(invoice, existing)
    assert len(results) == 1
    assert results[0].code == ValidationCode.NEAR_DUPLICATE_INVOICE
    assert results[0].severity.value == "warning"
