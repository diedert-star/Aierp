from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from aierp.enums import ValidationSeverity
from aierp.stage2_extraction.schemas import CanonicalInvoice
from aierp.stage3_validation.codes import ValidationCode, ValidationResult
from aierp.stage3_validation.iban import is_valid_iban
from aierp.stage3_validation.vat_number import is_structurally_valid_vat_number
from aierp.stage3_validation.vies_client import ViesClient

ARITHMETIC_TOLERANCE = Decimal("0.02")
MAX_INVOICE_AGE_MONTHS = 24
NEAR_DUPLICATE_WINDOW_DAYS = 5


@dataclass
class BookedInvoice:
    supplier_vat_number: str | None
    invoice_number: str
    gross_amount: Decimal
    invoice_date: date


@dataclass
class ValidationContext:
    tenant_vat_number: str
    vies_client: ViesClient
    existing_invoices: list[BookedInvoice] = field(default_factory=list)
    today: date = field(default_factory=date.today)


def _result(
    code: ValidationCode, severity: ValidationSeverity, message_nl: str, **params: str
) -> ValidationResult:
    return ValidationResult(code=code, severity=severity, message_nl=message_nl, params=params)


def check_vat_rate_arithmetic(invoice: CanonicalInvoice) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for entry in invoice.vat_breakdown:
        expected = (entry.taxable_base * entry.rate).quantize(Decimal("0.01"))
        difference = abs(expected - entry.vat_amount)
        if difference > ARITHMETIC_TOLERANCE:
            results.append(
                _result(
                    ValidationCode.VAT_RATE_ARITHMETIC_MISMATCH,
                    ValidationSeverity.ERROR,
                    (
                        f"BTW-bedrag wijkt {difference} EUR af van het berekende bedrag "
                        f"({entry.rate * 100}% van {entry.taxable_base} EUR = {expected} EUR, "
                        f"factuur vermeldt {entry.vat_amount} EUR)"
                    ),
                    rate=str(entry.rate),
                    taxable_base=str(entry.taxable_base),
                    expected_vat=str(expected),
                    actual_vat=str(entry.vat_amount),
                )
            )
    return results


def check_vat_breakdown_total(invoice: CanonicalInvoice) -> list[ValidationResult]:
    total = sum((entry.vat_amount for entry in invoice.vat_breakdown), Decimal("0"))
    difference = abs(total - invoice.totals.vat)
    if difference > ARITHMETIC_TOLERANCE:
        return [
            _result(
                ValidationCode.VAT_BREAKDOWN_TOTAL_MISMATCH,
                ValidationSeverity.ERROR,
                (
                    f"Som van de BTW-uitsplitsing ({total} EUR) komt niet overeen met het "
                    f"totale BTW-bedrag op de factuur ({invoice.totals.vat} EUR)"
                ),
                expected=str(total),
                actual=str(invoice.totals.vat),
            )
        ]
    return []


def check_line_net_total(invoice: CanonicalInvoice) -> list[ValidationResult]:
    total = sum((line.net_amount for line in invoice.lines), Decimal("0"))
    difference = abs(total - invoice.totals.net)
    if difference > ARITHMETIC_TOLERANCE:
        return [
            _result(
                ValidationCode.LINE_NET_TOTAL_MISMATCH,
                ValidationSeverity.ERROR,
                (
                    f"Som van de factuurregels ({total} EUR) komt niet overeen met het "
                    f"netto totaalbedrag ({invoice.totals.net} EUR)"
                ),
                expected=str(total),
                actual=str(invoice.totals.net),
            )
        ]
    return []


def check_totals_gross(invoice: CanonicalInvoice) -> list[ValidationResult]:
    expected_gross = invoice.totals.net + invoice.totals.vat
    difference = abs(expected_gross - invoice.totals.gross)
    if difference > ARITHMETIC_TOLERANCE:
        return [
            _result(
                ValidationCode.TOTALS_GROSS_MISMATCH,
                ValidationSeverity.ERROR,
                (
                    f"Netto ({invoice.totals.net} EUR) plus BTW ({invoice.totals.vat} EUR) "
                    f"komt niet overeen met het bruto totaalbedrag ({invoice.totals.gross} EUR)"
                ),
                net=str(invoice.totals.net),
                vat=str(invoice.totals.vat),
                gross=str(invoice.totals.gross),
            )
        ]
    return []


def check_supplier_vat_structural(invoice: CanonicalInvoice) -> list[ValidationResult]:
    vat_number = invoice.supplier.vat_number
    if vat_number is None or not is_structurally_valid_vat_number(vat_number):
        return [
            _result(
                ValidationCode.SUPPLIER_VAT_STRUCTURALLY_INVALID,
                ValidationSeverity.ERROR,
                f"BTW-nummer van de leverancier ({vat_number or 'ontbreekt'}) "
                "heeft geen geldig formaat",
                vat_number=vat_number or "",
            )
        ]
    return []


def check_supplier_vat_vies(
    invoice: CanonicalInvoice, vies_client: ViesClient
) -> list[ValidationResult]:
    vat_number = invoice.supplier.vat_number
    if vat_number is None or not is_structurally_valid_vat_number(vat_number):
        # Structural check already reports this; a malformed number can't be looked up.
        return []

    country_code = vat_number[:2]
    number_part = vat_number[2:]
    is_valid = vies_client.is_valid(country_code, number_part)

    if is_valid is None:
        return [
            _result(
                ValidationCode.VIES_UNAVAILABLE,
                ValidationSeverity.WARNING,
                f"VIES-controle van BTW-nummer {vat_number} is momenteel niet beschikbaar",
                vat_number=vat_number,
            )
        ]
    if is_valid is False:
        return [
            _result(
                ValidationCode.SUPPLIER_VAT_VIES_INVALID,
                ValidationSeverity.ERROR,
                f"BTW-nummer {vat_number} van de leverancier is volgens VIES niet geldig",
                vat_number=vat_number,
            )
        ]
    return []


def check_supplier_iban(invoice: CanonicalInvoice) -> list[ValidationResult]:
    iban = invoice.supplier.iban
    if iban is None:
        return []
    if not is_valid_iban(iban):
        return [
            _result(
                ValidationCode.SUPPLIER_IBAN_CHECKSUM_INVALID,
                ValidationSeverity.ERROR,
                f"IBAN {iban} van de leverancier heeft een ongeldige controlesom",
                iban=iban,
            )
        ]
    return []


def check_invoice_date(invoice: CanonicalInvoice, today: date) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    if invoice.invoice_date > today:
        results.append(
            _result(
                ValidationCode.INVOICE_DATE_IN_FUTURE,
                ValidationSeverity.ERROR,
                f"Factuurdatum {invoice.invoice_date.isoformat()} ligt in de toekomst",
                invoice_date=invoice.invoice_date.isoformat(),
            )
        )
    months_old = (today.year - invoice.invoice_date.year) * 12 + (
        today.month - invoice.invoice_date.month
    )
    if months_old > MAX_INVOICE_AGE_MONTHS:
        results.append(
            _result(
                ValidationCode.INVOICE_DATE_TOO_OLD,
                ValidationSeverity.WARNING,
                f"Factuurdatum {invoice.invoice_date.isoformat()} is ouder dan 24 maanden",
                invoice_date=invoice.invoice_date.isoformat(),
                months_old=str(months_old),
            )
        )
    return results


def check_buyer_vat(invoice: CanonicalInvoice, tenant_vat_number: str) -> list[ValidationResult]:
    if invoice.buyer.vat_number != tenant_vat_number:
        return [
            _result(
                ValidationCode.BUYER_VAT_MISMATCH,
                ValidationSeverity.ERROR,
                (
                    f"BTW-nummer van de koper ({invoice.buyer.vat_number or 'ontbreekt'}) "
                    f"komt niet overeen met het eigen BTW-nummer ({tenant_vat_number})"
                ),
                expected=tenant_vat_number,
                actual=invoice.buyer.vat_number or "",
            )
        ]
    return []


def check_currency(invoice: CanonicalInvoice) -> list[ValidationResult]:
    if invoice.currency != "EUR":
        return [
            _result(
                ValidationCode.CURRENCY_NOT_EUR,
                ValidationSeverity.WARNING,
                f"Factuur is opgesteld in {invoice.currency} in plaats van EUR",
                currency=invoice.currency,
            )
        ]
    return []


def check_duplicate(
    invoice: CanonicalInvoice, existing_invoices: list[BookedInvoice]
) -> list[ValidationResult]:
    for existing in existing_invoices:
        if (
            existing.supplier_vat_number == invoice.supplier.vat_number
            and existing.invoice_number == invoice.invoice_number
        ):
            return [
                _result(
                    ValidationCode.DUPLICATE_INVOICE,
                    ValidationSeverity.ERROR,
                    (
                        f"Factuur {invoice.invoice_number} van deze leverancier is al eerder "
                        "verwerkt"
                    ),
                    invoice_number=invoice.invoice_number,
                )
            ]
    return []


def check_near_duplicate(
    invoice: CanonicalInvoice, existing_invoices: list[BookedInvoice]
) -> list[ValidationResult]:
    for existing in existing_invoices:
        if (
            existing.supplier_vat_number == invoice.supplier.vat_number
            and existing.invoice_number != invoice.invoice_number
            and existing.gross_amount == invoice.totals.gross
            and abs((existing.invoice_date - invoice.invoice_date).days)
            <= NEAR_DUPLICATE_WINDOW_DAYS
        ):
            return [
                _result(
                    ValidationCode.NEAR_DUPLICATE_INVOICE,
                    ValidationSeverity.WARNING,
                    (
                        f"Mogelijk duplicaat: factuur {existing.invoice_number} van dezelfde "
                        f"leverancier voor hetzelfde bedrag ({invoice.totals.gross} EUR) binnen "
                        f"{NEAR_DUPLICATE_WINDOW_DAYS} dagen"
                    ),
                    existing_invoice_number=existing.invoice_number,
                    days_apart=str(abs((existing.invoice_date - invoice.invoice_date).days)),
                )
            ]
    return []
