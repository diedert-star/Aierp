import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aierp.config import settings
from aierp.enums import AliasType, CounterpartyStatus, MatchStrategy
from aierp.stage2_extraction.schemas import Party
from aierp.stage4_counterparty.models import Counterparty, CounterpartyAlias
from aierp.stage4_counterparty.normalize import (
    normalize_iban,
    normalize_name,
    normalize_vat_number,
)
from aierp.stage4_counterparty.schemas import CounterpartyMatch


def _find_by_alias(
    session: Session, tenant_id: str, alias_type: AliasType, normalized_value: str
) -> uuid.UUID | None:
    return session.execute(
        select(CounterpartyAlias.counterparty_id).where(
            CounterpartyAlias.tenant_id == tenant_id,
            CounterpartyAlias.alias_type == alias_type,
            CounterpartyAlias.normalized_value == normalized_value,
        )
    ).scalar_one_or_none()


def _find_best_fuzzy_name_match(
    session: Session, tenant_id: str, normalized_name: str, threshold: float
) -> tuple[uuid.UUID, float] | None:
    score = func.similarity(CounterpartyAlias.normalized_value, normalized_name)
    row = session.execute(
        select(CounterpartyAlias.counterparty_id, score.label("score"))
        .where(
            CounterpartyAlias.tenant_id == tenant_id,
            CounterpartyAlias.alias_type == AliasType.NAME,
            score >= threshold,
        )
        .order_by(score.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return row.counterparty_id, float(row.score)


def _record_alias(
    session: Session,
    *,
    counterparty_id: uuid.UUID,
    tenant_id: str,
    alias_type: AliasType,
    raw_value: str,
    normalized_value: str,
) -> None:
    exists = session.execute(
        select(CounterpartyAlias.id).where(
            CounterpartyAlias.tenant_id == tenant_id,
            CounterpartyAlias.alias_type == alias_type,
            CounterpartyAlias.normalized_value == normalized_value,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return
    session.add(
        CounterpartyAlias(
            counterparty_id=counterparty_id,
            tenant_id=tenant_id,
            alias_type=alias_type,
            raw_value=raw_value,
            normalized_value=normalized_value,
        )
    )


def _record_all_aliases(
    session: Session, *, counterparty_id: uuid.UUID, tenant_id: str, supplier: Party
) -> None:
    if supplier.name:
        _record_alias(
            session,
            counterparty_id=counterparty_id,
            tenant_id=tenant_id,
            alias_type=AliasType.NAME,
            raw_value=supplier.name,
            normalized_value=normalize_name(supplier.name),
        )
    if supplier.vat_number:
        _record_alias(
            session,
            counterparty_id=counterparty_id,
            tenant_id=tenant_id,
            alias_type=AliasType.VAT_NUMBER,
            raw_value=supplier.vat_number,
            normalized_value=normalize_vat_number(supplier.vat_number),
        )
    if supplier.iban:
        _record_alias(
            session,
            counterparty_id=counterparty_id,
            tenant_id=tenant_id,
            alias_type=AliasType.IBAN,
            raw_value=supplier.iban,
            normalized_value=normalize_iban(supplier.iban),
        )
    session.flush()


def resolve_counterparty(
    session: Session,
    tenant_id: str,
    supplier: Party,
    *,
    fuzzy_name_match_threshold: float | None = None,
) -> CounterpartyMatch:
    threshold = (
        fuzzy_name_match_threshold
        if fuzzy_name_match_threshold is not None
        else settings.fuzzy_name_match_threshold
    )

    if supplier.vat_number:
        counterparty_id = _find_by_alias(
            session, tenant_id, AliasType.VAT_NUMBER, normalize_vat_number(supplier.vat_number)
        )
        if counterparty_id is not None:
            _record_all_aliases(
                session, counterparty_id=counterparty_id, tenant_id=tenant_id, supplier=supplier
            )
            return CounterpartyMatch(
                counterparty_id=counterparty_id,
                strategy=MatchStrategy.VAT_EXACT,
                confidence=1.0,
                is_provisional=False,
            )

    if supplier.iban:
        counterparty_id = _find_by_alias(
            session, tenant_id, AliasType.IBAN, normalize_iban(supplier.iban)
        )
        if counterparty_id is not None:
            _record_all_aliases(
                session, counterparty_id=counterparty_id, tenant_id=tenant_id, supplier=supplier
            )
            return CounterpartyMatch(
                counterparty_id=counterparty_id,
                strategy=MatchStrategy.IBAN_EXACT,
                confidence=1.0,
                is_provisional=False,
            )

    if supplier.name:
        fuzzy_match = _find_best_fuzzy_name_match(
            session, tenant_id, normalize_name(supplier.name), threshold
        )
        if fuzzy_match is not None:
            counterparty_id, score = fuzzy_match
            _record_all_aliases(
                session, counterparty_id=counterparty_id, tenant_id=tenant_id, supplier=supplier
            )
            return CounterpartyMatch(
                counterparty_id=counterparty_id,
                strategy=MatchStrategy.FUZZY_NAME,
                confidence=score,
                is_provisional=True,
            )

    new_counterparty = Counterparty(
        tenant_id=tenant_id,
        display_name=supplier.name or "Onbekende leverancier",
        status=CounterpartyStatus.UNCONFIRMED,
    )
    session.add(new_counterparty)
    session.flush()
    _record_all_aliases(
        session, counterparty_id=new_counterparty.id, tenant_id=tenant_id, supplier=supplier
    )
    return CounterpartyMatch(
        counterparty_id=new_counterparty.id,
        strategy=MatchStrategy.NEW,
        confidence=1.0,
        is_provisional=True,
    )
