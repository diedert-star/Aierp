import enum


class Channel(enum.StrEnum):
    PEPPOL = "peppol"
    EMAIL = "email"
    UPLOAD = "upload"
    MOBILE = "mobile"


class IngestStatus(enum.StrEnum):
    RECEIVED = "received"


class ValidationSeverity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"


class AliasType(enum.StrEnum):
    NAME = "name"
    VAT_NUMBER = "vat_number"
    IBAN = "iban"


class CounterpartyStatus(enum.StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class MatchStrategy(enum.StrEnum):
    VAT_EXACT = "vat_exact"
    IBAN_EXACT = "iban_exact"
    FUZZY_NAME = "fuzzy_name"
    NEW = "new"


class DocumentStatus(enum.StrEnum):
    CLEAN = "clean"
    NEEDS_REVIEW = "needs_review"
