import enum

from pydantic import BaseModel

from aierp.enums import ValidationSeverity


class ValidationCode(enum.StrEnum):
    VAT_RATE_ARITHMETIC_MISMATCH = "vat_rate_arithmetic_mismatch"
    VAT_BREAKDOWN_TOTAL_MISMATCH = "vat_breakdown_total_mismatch"
    LINE_NET_TOTAL_MISMATCH = "line_net_total_mismatch"
    TOTALS_GROSS_MISMATCH = "totals_gross_mismatch"
    SUPPLIER_VAT_STRUCTURALLY_INVALID = "supplier_vat_structurally_invalid"
    SUPPLIER_VAT_VIES_INVALID = "supplier_vat_vies_invalid"
    VIES_UNAVAILABLE = "vies_unavailable"
    SUPPLIER_IBAN_CHECKSUM_INVALID = "supplier_iban_checksum_invalid"
    INVOICE_DATE_IN_FUTURE = "invoice_date_in_future"
    INVOICE_DATE_TOO_OLD = "invoice_date_too_old"
    BUYER_VAT_MISMATCH = "buyer_vat_mismatch"
    CURRENCY_NOT_EUR = "currency_not_eur"
    DUPLICATE_INVOICE = "duplicate_invoice"
    NEAR_DUPLICATE_INVOICE = "near_duplicate_invoice"


class ValidationResult(BaseModel):
    code: ValidationCode
    severity: ValidationSeverity
    message_nl: str
    params: dict[str, str]
