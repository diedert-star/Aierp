import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aierp.db import Base
from aierp.db_enum import pg_enum
from aierp.enums import Channel, IngestStatus


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="uq_source_document_tenant_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    blob_key: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[Channel] = mapped_column(pg_enum(Channel, "channel"), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingest_status: Mapped[IngestStatus] = mapped_column(
        pg_enum(IngestStatus, "ingest_status"),
        nullable=False,
        default=IngestStatus.RECEIVED,
    )
