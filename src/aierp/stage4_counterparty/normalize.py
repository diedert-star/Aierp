import re

_LEGAL_FORMS = {
    "bv",
    "nv",
    "bvba",
    "vof",
    "cv",
    "cvba",
    "vzw",
    "gmbh",
    "sa",
    "sarl",
    "srl",
    "eenmanszaak",
}
_PUNCTUATION_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip legal-form suffixes and punctuation, collapse whitespace."""
    text = _PUNCTUATION_PATTERN.sub(" ", name.lower())
    tokens = [token for token in text.split() if token not in _LEGAL_FORMS]
    return _WHITESPACE_PATTERN.sub(" ", " ".join(tokens)).strip()


def normalize_vat_number(vat_number: str) -> str:
    return vat_number.strip().upper().replace(" ", "")


def normalize_iban(iban: str) -> str:
    return iban.strip().upper().replace(" ", "")
