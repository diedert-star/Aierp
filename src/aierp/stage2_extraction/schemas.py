import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Party(BaseModel):
    name: str
    vat_number: str | None = None
    kbo_or_kvk_number: str | None = None
    iban: str | None = None
    address: str | None = None
    country_code: str | None = None


class InvoiceLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    net_amount: Decimal
    vat_rate: Decimal
    vat_amount: Decimal


class VatBreakdownEntry(BaseModel):
    rate: Decimal
    taxable_base: Decimal
    vat_amount: Decimal
    exemption_reason_code: str | None = None


class Totals(BaseModel):
    net: Decimal
    vat: Decimal
    gross: Decimal
    prepaid: Decimal
    payable: Decimal


class ExtractorInfo(BaseModel):
    name: str
    version: str


class CanonicalInvoice(BaseModel):
    document_id: uuid.UUID
    supplier: Party
    buyer: Party
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    currency: str
    lines: list[InvoiceLine]
    vat_breakdown: list[VatBreakdownEntry]
    totals: Totals
    payment_reference: str | None = None
    extraction_confidence: dict[str, float]
    extractor: ExtractorInfo
