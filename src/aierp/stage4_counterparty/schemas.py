import uuid

from pydantic import BaseModel

from aierp.enums import MatchStrategy


class CounterpartyMatch(BaseModel):
    counterparty_id: uuid.UUID
    strategy: MatchStrategy
    confidence: float
    is_provisional: bool
