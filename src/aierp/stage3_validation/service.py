from aierp.stage2_extraction.schemas import CanonicalInvoice
from aierp.stage3_validation.checks import (
    ValidationContext,
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
from aierp.stage3_validation.codes import ValidationResult


def run_all_checks(invoice: CanonicalInvoice, context: ValidationContext) -> list[ValidationResult]:
    """Runs every check unconditionally and concatenates results — no short-circuiting."""
    results: list[ValidationResult] = []
    results += check_vat_rate_arithmetic(invoice)
    results += check_vat_breakdown_total(invoice)
    results += check_line_net_total(invoice)
    results += check_totals_gross(invoice)
    results += check_supplier_vat_structural(invoice)
    results += check_supplier_vat_vies(invoice, context.vies_client)
    results += check_supplier_iban(invoice)
    results += check_invoice_date(invoice, context.today)
    results += check_buyer_vat(invoice, context.tenant_vat_number)
    results += check_currency(invoice)
    results += check_duplicate(invoice, context.existing_invoices)
    results += check_near_duplicate(invoice, context.existing_invoices)
    return results
