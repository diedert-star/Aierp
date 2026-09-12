import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aierp.db import Base
from aierp.db_enum import pg_enum
from aierp.enums import DocumentStatus, MatchStrategy


class DocumentPipelineState(Base):
    __tablename__ = "document_pipeline_state"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_document.id"), primary_key=True
    )
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"), nullable=False
    )
    reasons: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    canonical_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_invoice.id"), nullable=True
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("counterparty.id"), nullable=True
    )
    counterparty_match_strategy: Mapped[MatchStrategy | None] = mapped_column(
        pg_enum(MatchStrategy, "match_strategy"), nullable=True
    )
    counterparty_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
