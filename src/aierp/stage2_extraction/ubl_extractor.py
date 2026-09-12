import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from aierp.stage2_extraction.schemas import (
    CanonicalInvoice,
    ExtractorInfo,
    InvoiceLine,
    Party,
    Totals,
    VatBreakdownEntry,
)

CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"
CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"


class UblExtractionError(ValueError):
    """Raised when a UBL document is missing an EN 16931 core field required to extract."""


def _find_text(element: etree._Element | None, path: str) -> str | None:
    if element is None:
        return None
    found = element.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _to_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


class _ConfidenceTracker:
    def __init__(self) -> None:
        self.values: dict[str, float] = {}

    def record(self, field_path: str, value: object) -> None:
        if value is not None:
            self.values[field_path] = 1.0


def _extract_party(
    party_el: etree._Element | None, prefix: str, confidence: _ConfidenceTracker
) -> Party:
    if party_el is None:
        return Party(name="")

    name = _find_text(party_el, f"{CAC}PartyName/{CBC}Name") or _find_text(
        party_el, f"{CAC}PartyLegalEntity/{CBC}RegistrationName"
    )
    confidence.record(f"{prefix}.name", name)

    vat_number = None
    for tax_scheme_el in party_el.findall(f"{CAC}PartyTaxScheme"):
        scheme_id = _find_text(tax_scheme_el, f"{CAC}TaxScheme/{CBC}ID")
        if scheme_id == "VAT":
            vat_number = _find_text(tax_scheme_el, f"{CBC}CompanyID")
            break
    confidence.record(f"{prefix}.vat_number", vat_number)

    kbo_or_kvk_number = _find_text(party_el, f"{CAC}PartyLegalEntity/{CBC}CompanyID")
    confidence.record(f"{prefix}.kbo_or_kvk_number", kbo_or_kvk_number)

    postal_address = party_el.find(f"{CAC}PostalAddress")
    address = None
    country_code = None
    if postal_address is not None:
        street = _find_text(postal_address, f"{CBC}StreetName")
        city = _find_text(postal_address, f"{CBC}CityName")
        postal_zone = _find_text(postal_address, f"{CBC}PostalZone")
        address_parts = [p for p in (street, postal_zone, city) if p]
        address = ", ".join(address_parts) or None
        country_code = _find_text(postal_address, f"{CAC}Country/{CBC}IdentificationCode")
    confidence.record(f"{prefix}.address", address)
    confidence.record(f"{prefix}.country_code", country_code)

    return Party(
        name=name or "",
        vat_number=vat_number,
        kbo_or_kvk_number=kbo_or_kvk_number,
        iban=None,
        address=address,
        country_code=country_code,
    )


def _extract_lines(root: etree._Element, confidence: _ConfidenceTracker) -> list[InvoiceLine]:
    lines: list[InvoiceLine] = []
    for index, line_el in enumerate(root.findall(f"{CAC}InvoiceLine")):
        description = _find_text(line_el, f"{CAC}Item/{CBC}Name") or ""
        quantity = _to_decimal(_find_text(line_el, f"{CBC}InvoicedQuantity")) or Decimal(0)
        unit_price = _to_decimal(_find_text(line_el, f"{CAC}Price/{CBC}PriceAmount")) or Decimal(0)
        net_amount = _to_decimal(_find_text(line_el, f"{CBC}LineExtensionAmount")) or Decimal(0)
        rate_percent = _to_decimal(
            _find_text(line_el, f"{CAC}Item/{CAC}ClassifiedTaxCategory/{CBC}Percent")
        ) or Decimal(0)
        vat_rate = rate_percent / Decimal(100)
        vat_amount = (net_amount * vat_rate).quantize(Decimal("0.01"))

        prefix = f"lines[{index}]"
        confidence.record(f"{prefix}.description", description or None)
        confidence.record(f"{prefix}.quantity", quantity)
        confidence.record(f"{prefix}.unit_price", unit_price)
        confidence.record(f"{prefix}.net_amount", net_amount)
        confidence.record(f"{prefix}.vat_rate", vat_rate)
        confidence.record(f"{prefix}.vat_amount", vat_amount)

        lines.append(
            InvoiceLine(
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                net_amount=net_amount,
                vat_rate=vat_rate,
                vat_amount=vat_amount,
            )
        )
    return lines


def _extract_vat_breakdown(
    root: etree._Element, confidence: _ConfidenceTracker
) -> list[VatBreakdownEntry]:
    breakdown: list[VatBreakdownEntry] = []
    tax_total = root.find(f"{CAC}TaxTotal")
    if tax_total is None:
        return breakdown

    for index, subtotal_el in enumerate(tax_total.findall(f"{CAC}TaxSubtotal")):
        rate_percent = _to_decimal(
            _find_text(subtotal_el, f"{CAC}TaxCategory/{CBC}Percent")
        ) or Decimal(0)
        taxable_base = _to_decimal(_find_text(subtotal_el, f"{CBC}TaxableAmount")) or Decimal(0)
        vat_amount = _to_decimal(_find_text(subtotal_el, f"{CBC}TaxAmount")) or Decimal(0)
        exemption_reason_code = _find_text(
            subtotal_el, f"{CAC}TaxCategory/{CBC}TaxExemptionReasonCode"
        )

        prefix = f"vat_breakdown[{index}]"
        confidence.record(f"{prefix}.rate", rate_percent)
        confidence.record(f"{prefix}.taxable_base", taxable_base)
        confidence.record(f"{prefix}.vat_amount", vat_amount)
        confidence.record(f"{prefix}.exemption_reason_code", exemption_reason_code)

        breakdown.append(
            VatBreakdownEntry(
                rate=rate_percent / Decimal(100),
                taxable_base=taxable_base,
                vat_amount=vat_amount,
                exemption_reason_code=exemption_reason_code,
            )
        )
    return breakdown


class UblExtractor:
    """Parses UBL 2.1 / Peppol BIS Billing 3.0 invoices, mapping EN 16931 core fields directly.

    Confidence is 1.0 for every field present in the source XML. Elements outside the
    EN 16931 core model (CIUS/extension content) are simply not queried — they neither
    fail extraction nor appear in the canonical record.
    """

    name = "ubl"
    version = "1.0.0"

    def extract(self, raw_bytes: bytes, *, document_id: uuid.UUID) -> CanonicalInvoice:
        try:
            root = etree.fromstring(raw_bytes)
        except etree.XMLSyntaxError as exc:
            raise UblExtractionError(f"not well-formed XML: {exc}") from exc

        confidence = _ConfidenceTracker()

        invoice_number = _find_text(root, f"{CBC}ID")
        issue_date_text = _find_text(root, f"{CBC}IssueDate")
        if invoice_number is None or issue_date_text is None:
            raise UblExtractionError(
                "missing required EN 16931 core field: cbc:ID and cbc:IssueDate are mandatory"
            )
        confidence.record("invoice_number", invoice_number)
        confidence.record("invoice_date", issue_date_text)

        due_date = _to_date(_find_text(root, f"{CBC}DueDate"))
        confidence.record("due_date", due_date)

        currency = _find_text(root, f"{CBC}DocumentCurrencyCode") or "EUR"
        confidence.record("currency", currency)

        supplier = _extract_party(
            root.find(f"{CAC}AccountingSupplierParty/{CAC}Party"), "supplier", confidence
        )
        buyer = _extract_party(
            root.find(f"{CAC}AccountingCustomerParty/{CAC}Party"), "buyer", confidence
        )

        payment_means = root.find(f"{CAC}PaymentMeans")
        supplier.iban = _find_text(payment_means, f"{CAC}PayeeFinancialAccount/{CBC}ID")
        confidence.record("supplier.iban", supplier.iban)

        payment_reference = _find_text(payment_means, f"{CBC}PaymentID")
        confidence.record("payment_reference", payment_reference)

        lines = _extract_lines(root, confidence)
        vat_breakdown = _extract_vat_breakdown(root, confidence)

        monetary_total = root.find(f"{CAC}LegalMonetaryTotal")
        net = _to_decimal(_find_text(monetary_total, f"{CBC}TaxExclusiveAmount")) or Decimal(0)
        gross = _to_decimal(_find_text(monetary_total, f"{CBC}TaxInclusiveAmount")) or Decimal(0)
        prepaid = _to_decimal(_find_text(monetary_total, f"{CBC}PrepaidAmount")) or Decimal(0)
        payable = _to_decimal(_find_text(monetary_total, f"{CBC}PayableAmount")) or Decimal(0)
        vat = _to_decimal(_find_text(root, f"{CAC}TaxTotal/{CBC}TaxAmount")) or Decimal(0)

        confidence.record("totals.net", net)
        confidence.record("totals.vat", vat)
        confidence.record("totals.gross", gross)
        confidence.record("totals.prepaid", prepaid)
        confidence.record("totals.payable", payable)

        return CanonicalInvoice(
            document_id=document_id,
            supplier=supplier,
            buyer=buyer,
            invoice_number=invoice_number,
            invoice_date=date.fromisoformat(issue_date_text),
            due_date=due_date,
            currency=currency,
            lines=lines,
            vat_breakdown=vat_breakdown,
            totals=Totals(net=net, vat=vat, gross=gross, prepaid=prepaid, payable=payable),
            payment_reference=payment_reference,
            extraction_confidence=confidence.values,
            extractor=ExtractorInfo(name=self.name, version=self.version),
        )
