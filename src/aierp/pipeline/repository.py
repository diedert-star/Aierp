import uuid

from sqlalchemy.orm import Session

from aierp.enums import DocumentStatus, MatchStrategy
from aierp.pipeline.models import DocumentPipelineState
from aierp.pipeline.reasons import ReviewReason
from aierp.stage1_ingest.models import SourceDocument


def upsert_pipeline_state(
    session: Session,
    *,
    document_id: uuid.UUID,
    status: DocumentStatus,
    reasons: list[ReviewReason],
    canonical_invoice_id: uuid.UUID | None,
    counterparty_id: uuid.UUID | None,
    counterparty_match_strategy: MatchStrategy | None,
    counterparty_match_confidence: float | None,
) -> DocumentPipelineState:
    state = session.get(DocumentPipelineState, document_id)
    reasons_data = [reason.model_dump() for reason in reasons]

    if state is None:
        state = DocumentPipelineState(document_id=document_id)
        session.add(state)

    state.status = status
    state.reasons = reasons_data
    state.canonical_invoice_id = canonical_invoice_id
    state.counterparty_id = counterparty_id
    state.counterparty_match_strategy = counterparty_match_strategy
    state.counterparty_match_confidence = counterparty_match_confidence
    session.flush()
    return state


def list_pipeline_states(
    session: Session, *, tenant_id: str, status: DocumentStatus | None = None
) -> list[DocumentPipelineState]:
    query = session.query(DocumentPipelineState).join(
        SourceDocument, SourceDocument.id == DocumentPipelineState.document_id
    ).filter(SourceDocument.tenant_id == tenant_id)
    if status is not None:
        query = query.filter(DocumentPipelineState.status == status)
    return query.all()
