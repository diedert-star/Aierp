import pytest

from aierp.stage3_validation.vat_number import is_structurally_valid_vat_number


@pytest.mark.parametrize(
    "vat_number",
    [
        "BE0123456749",
        "NL123456789B01",
        "DE123456789",
        "LU12345678",
    ],
)
def test_valid_formats(vat_number: str) -> None:
    assert is_structurally_valid_vat_number(vat_number) is True


@pytest.mark.parametrize(
    "vat_number",
    [
        "BE12",
        "NL123456789",
        "DE12",
        "",
    ],
)
def test_invalid_formats(vat_number: str) -> None:
    assert is_structurally_valid_vat_number(vat_number) is False
