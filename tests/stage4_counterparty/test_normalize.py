from aierp.stage4_counterparty.normalize import normalize_iban, normalize_name, normalize_vat_number


def test_strips_legal_form_suffix_and_lowercases() -> None:
    assert normalize_name("Acme Leverancier BV") == "acme leverancier"


def test_strips_punctuation() -> None:
    assert normalize_name("De Kleine Bakker, V.O.F.") == "de kleine bakker v o f"


def test_different_legal_forms_normalize_to_the_same_base_name() -> None:
    assert normalize_name("Nutrimax BVBA") == "nutrimax"
    assert normalize_name("Nutrimax NV") == "nutrimax"
    assert normalize_name("Nutrimax GmbH") == "nutrimax"


def test_normalize_vat_number_strips_spaces_and_uppercases() -> None:
    assert normalize_vat_number("be 0123456749") == "BE0123456749"


def test_normalize_iban_strips_spaces_and_uppercases() -> None:
    assert normalize_iban("be68 5390 0754 7034") == "BE68539007547034"
