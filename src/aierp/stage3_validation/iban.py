import re

_IBAN_PATTERN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def is_valid_iban(iban: str) -> bool:
    candidate = iban.strip().upper().replace(" ", "")
    if not _IBAN_PATTERN.match(candidate):
        return False

    rearranged = candidate[4:] + candidate[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1
