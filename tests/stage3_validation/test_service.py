from datetime import timedelta
from decimal import Decimal

from aierp.stage3_validation.checks import ValidationContext
from aierp.stage3_validation.codes import ValidationCode
from aierp.stage3_validation.service import run_all_checks
from tests.stage3_validation.factories import (
    DEFAULT_INVOICE_DATE,
    DEFAULT_TENANT_VAT,
    make_invoice,
)


class _AlwaysValidVies:
    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        return True


def test_clean_invoice_produces_no_results() -> None:
    invoice = make_invoice()
    context = ValidationContext(
        tenant_vat_number=DEFAULT_TENANT_VAT,
        vies_client=_AlwaysValidVies(),
        today=DEFAULT_INVOICE_DATE + timedelta(days=1),
    )
    assert run_all_checks(invoice, context) == []


def test_all_checks_run_even_when_several_fail_at_once() -> None:
    # Bad arithmetic AND a malformed VAT AND wrong buyer AND non-EUR currency all at once —
    # every failing check must still be reported, not just the first one.
    invoice = make_invoice(
        net=Decimal("100.00"),
        vat=Decimal("999.00"),
        gross=Decimal("1099.00"),
        supplier_vat="BE12",
        buyer_vat="BE0111111111",
        currency="USD",
    )
    context = ValidationContext(
        tenant_vat_number=DEFAULT_TENANT_VAT, vies_client=_AlwaysValidVies()
    )

    results = run_all_checks(invoice, context)
    codes = {result.code for result in results}

    assert ValidationCode.VAT_RATE_ARITHMETIC_MISMATCH in codes
    assert ValidationCode.SUPPLIER_VAT_STRUCTURALLY_INVALID in codes
    assert ValidationCode.BUYER_VAT_MISMATCH in codes
    assert ValidationCode.CURRENCY_NOT_EUR in codes
