import re

# Structural patterns (format only, not the official check-digit algorithm — that's VIES's job).
_COUNTRY_PATTERNS: dict[str, re.Pattern[str]] = {
    "BE": re.compile(r"^BE[01]\d{9}$"),
    "NL": re.compile(r"^NL\d{9}B\d{2}$"),
    "DE": re.compile(r"^DE\d{9}$"),
    "FR": re.compile(r"^FR[A-Z0-9]{2}\d{9}$"),
    "LU": re.compile(r"^LU\d{8}$"),
}
_GENERIC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{2,12}$")


def is_structurally_valid_vat_number(vat_number: str) -> bool:
    candidate = vat_number.strip().upper().replace(" ", "")
    country_prefix = candidate[:2]
    pattern = _COUNTRY_PATTERNS.get(country_prefix)
    if pattern is not None:
        return bool(pattern.match(candidate))
    return bool(_GENERIC_PATTERN.match(candidate))
