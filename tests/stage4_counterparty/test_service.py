from sqlalchemy import select
from sqlalchemy.orm import Session

from aierp.enums import AliasType, MatchStrategy
from aierp.stage2_extraction.schemas import Party
from aierp.stage4_counterparty.models import Counterparty, CounterpartyAlias
from aierp.stage4_counterparty.service import resolve_counterparty

TENANT = "tenant-a"


def test_unknown_supplier_creates_provisional_counterparty(db_session: Session) -> None:
    supplier = Party(name="Nieuwe Leverancier CV", vat_number="BE0456789123")

    match = resolve_counterparty(db_session, TENANT, supplier)

    assert match.strategy == MatchStrategy.NEW
    assert match.is_provisional is True

    counterparty = db_session.get(Counterparty, match.counterparty_id)
    assert counterparty is not None
    assert counterparty.status.value == "unconfirmed"


def test_exact_vat_match_is_not_provisional(db_session: Session) -> None:
    first_supplier = Party(name="Acme Leverancier BV", vat_number="BE0123456749")
    first_match = resolve_counterparty(db_session, TENANT, first_supplier)

    second_supplier = Party(name="Acme Leverancier BV", vat_number="BE0123456749")
    second_match = resolve_counterparty(db_session, TENANT, second_supplier)

    assert second_match.strategy == MatchStrategy.VAT_EXACT
    assert second_match.is_provisional is False
    assert second_match.counterparty_id == first_match.counterparty_id


def test_exact_iban_match_when_vat_absent(db_session: Session) -> None:
    first_supplier = Party(
        name="Acme Leverancier BV", vat_number="BE0123456749", iban="BE68539007547034"
    )
    first_match = resolve_counterparty(db_session, TENANT, first_supplier)

    # second invoice omits the VAT number but carries the same IBAN
    second_supplier = Party(name="Acme Leverancier BV", iban="BE68539007547034")
    second_match = resolve_counterparty(db_session, TENANT, second_supplier)

    assert second_match.strategy == MatchStrategy.IBAN_EXACT
    assert second_match.is_provisional is False
    assert second_match.counterparty_id == first_match.counterparty_id


def test_fuzzy_name_match_proposes_but_is_provisional(db_session: Session) -> None:
    first_supplier = Party(name="Nutrimax BVBA")
    first_match = resolve_counterparty(db_session, TENANT, first_supplier)

    # same company, slightly different spelling/legal form, no VAT or IBAN on this invoice
    second_supplier = Party(name="Nutrimax N.V.")
    second_match = resolve_counterparty(db_session, TENANT, second_supplier)

    assert second_match.strategy == MatchStrategy.FUZZY_NAME
    assert second_match.is_provisional is True
    assert second_match.counterparty_id == first_match.counterparty_id


def test_fuzzy_name_match_never_returned_below_threshold(db_session: Session) -> None:
    first_supplier = Party(name="Nutrimax BVBA")
    resolve_counterparty(db_session, TENANT, first_supplier)

    unrelated_supplier = Party(name="Zonnepanelen Vlaanderen NV")
    match = resolve_counterparty(
        db_session, TENANT, unrelated_supplier, fuzzy_name_match_threshold=0.9
    )

    assert match.strategy == MatchStrategy.NEW


def test_resolution_records_every_alias_seen(db_session: Session) -> None:
    supplier = Party(name="Acme Leverancier BV", vat_number="BE0123456749", iban="BE68539007547034")
    match = resolve_counterparty(db_session, TENANT, supplier)

    aliases = db_session.execute(
        select(CounterpartyAlias).where(CounterpartyAlias.counterparty_id == match.counterparty_id)
    ).scalars().all()
    alias_types = {alias.alias_type for alias in aliases}

    assert alias_types == {AliasType.NAME, AliasType.VAT_NUMBER, AliasType.IBAN}


def test_different_tenants_never_share_counterparties(db_session: Session) -> None:
    supplier = Party(name="Acme Leverancier BV", vat_number="BE0123456749")
    match_a = resolve_counterparty(db_session, "tenant-a", supplier)
    match_b = resolve_counterparty(db_session, "tenant-b", supplier)

    assert match_a.counterparty_id != match_b.counterparty_id
    assert match_b.strategy == MatchStrategy.NEW
