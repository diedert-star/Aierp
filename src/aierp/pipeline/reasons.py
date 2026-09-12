import enum

from pydantic import BaseModel

from aierp.stage3_validation.codes import ValidationResult


class PipelineReasonCode(enum.StrEnum):
    FIRST_INVOICE_FROM_SUPPLIER = "first_invoice_from_supplier"
    COUNTERPARTY_UNCONFIRMED = "counterparty_unconfirmed"
    EXTRACTION_NOT_SUPPORTED = "extraction_not_supported"


class ReviewReason(BaseModel):
    code: str
    message_nl: str
    params: dict[str, str]


def reason_from_validation_result(result: ValidationResult) -> ReviewReason:
    return ReviewReason(code=result.code.value, message_nl=result.message_nl, params=result.params)


def first_invoice_from_supplier_reason() -> ReviewReason:
    return ReviewReason(
        code=PipelineReasonCode.FIRST_INVOICE_FROM_SUPPLIER.value,
        message_nl="Eerste factuur van deze leverancier",
        params={},
    )


def counterparty_unconfirmed_reason(candidate_name: str, confidence: float) -> ReviewReason:
    return ReviewReason(
        code=PipelineReasonCode.COUNTERPARTY_UNCONFIRMED.value,
        message_nl=(
            f"Leverancier komt mogelijk overeen met bestaande relatie '{candidate_name}' "
            f"(zekerheid {confidence:.0%}), controleer en bevestig"
        ),
        params={"candidate_name": candidate_name, "confidence": f"{confidence:.2f}"},
    )


def extraction_not_supported_reason(channel: str, mime_type: str) -> ReviewReason:
    return ReviewReason(
        code=PipelineReasonCode.EXTRACTION_NOT_SUPPORTED.value,
        message_nl=(
            f"Automatische verwerking van dit bestandstype ({mime_type}) wordt nog niet ondersteund"
        ),
        params={"channel": channel, "mime_type": mime_type},
    )
