import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from aierp.db import Base
from aierp.db_enum import pg_enum
from aierp.enums import ValidationSeverity
from aierp.stage3_validation.codes import ValidationCode


class ValidationRun(Base):
    __tablename__ = "validation_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_document.id"), nullable=False, index=True
    )
    canonical_invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_invoice.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ValidationResultRecord(Base):
    __tablename__ = "validation_result"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_run.id"), nullable=False, index=True
    )
    code: Mapped[ValidationCode] = mapped_column(
        pg_enum(ValidationCode, "validation_code"), nullable=False
    )
    severity: Mapped[ValidationSeverity] = mapped_column(
        pg_enum(ValidationSeverity, "validation_severity"), nullable=False
    )
    message_nl: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
