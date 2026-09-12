import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from aierp.db import Base
from aierp.db_enum import pg_enum
from aierp.enums import AliasType, CounterpartyStatus


class Counterparty(Base):
    __tablename__ = "counterparty"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[CounterpartyStatus] = mapped_column(
        pg_enum(CounterpartyStatus, "counterparty_status"),
        nullable=False,
        default=CounterpartyStatus.UNCONFIRMED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class CounterpartyAlias(Base):
    __tablename__ = "counterparty_alias"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "alias_type",
            "normalized_value",
            name="uq_counterparty_alias_tenant_type_value",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("counterparty.id"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    alias_type: Mapped[AliasType] = mapped_column(pg_enum(AliasType, "alias_type"), nullable=False)
    raw_value: Mapped[str] = mapped_column(String, nullable=False)
    normalized_value: Mapped[str] = mapped_column(String, index=True, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
