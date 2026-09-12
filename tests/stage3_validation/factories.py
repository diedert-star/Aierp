import uuid
from datetime import date
from decimal import Decimal

from aierp.stage2_extraction.schemas import (
    CanonicalInvoice,
    ExtractorInfo,
    InvoiceLine,
    Party,
    Totals,
    VatBreakdownEntry,
)

DEFAULT_TENANT_VAT = "BE0999999999"
DEFAULT_SUPPLIER_VAT = "BE0123456749"
DEFAULT_SUPPLIER_IBAN = "BE68539007547034"
DEFAULT_INVOICE_DATE = date(2024, 3, 15)


def make_invoice(
    *,
    invoice_number: str = "2024-0001",
    invoice_date: date = DEFAULT_INVOICE_DATE,
    currency: str = "EUR",
    supplier_vat: str | None = DEFAULT_SUPPLIER_VAT,
    supplier_iban: str | None = DEFAULT_SUPPLIER_IBAN,
    buyer_vat: str | None = DEFAULT_TENANT_VAT,
    net: Decimal = Decimal("100.00"),
    vat: Decimal = Decimal("21.00"),
    gross: Decimal = Decimal("121.00"),
    rate: Decimal = Decimal("0.21"),
) -> CanonicalInvoice:
    return CanonicalInvoice(
        document_id=uuid.uuid4(),
        supplier=Party(name="Acme Leverancier BV", vat_number=supplier_vat, iban=supplier_iban),
        buyer=Party(name="Klant NV", vat_number=buyer_vat),
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=None,
        currency=currency,
        lines=[
            InvoiceLine(
                description="Diensten",
                quantity=Decimal("1"),
                unit_price=net,
                net_amount=net,
                vat_rate=rate,
                vat_amount=vat,
            )
        ],
        vat_breakdown=[
            VatBreakdownEntry(
                rate=rate, taxable_base=net, vat_amount=vat, exemption_reason_code=None
            )
        ],
        totals=Totals(net=net, vat=vat, gross=gross, prepaid=Decimal("0.00"), payable=gross),
        payment_reference=None,
        extraction_confidence={},
        extractor=ExtractorInfo(name="ubl", version="1.0.0"),
    )
