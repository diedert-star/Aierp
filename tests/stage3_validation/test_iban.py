from aierp.stage3_validation.iban import is_valid_iban


def test_valid_belgian_iban() -> None:
    assert is_valid_iban("BE68539007547034") is True


def test_valid_dutch_iban() -> None:
    assert is_valid_iban("NL91ABNA0417164300") is True


def test_iban_with_bad_checksum_is_invalid() -> None:
    assert is_valid_iban("BE00000000000000") is False


def test_iban_with_wrong_format_is_invalid() -> None:
    assert is_valid_iban("not an iban") is False


def test_iban_accepts_spaces_and_lowercase() -> None:
    assert is_valid_iban("be68 5390 0754 7034") is True
