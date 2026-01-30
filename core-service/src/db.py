import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    LargeBinary,
    String,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(str(settings.database.url))
SessionLocal = sessionmaker(bind=engine)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_price: Mapped[float] = mapped_column(Float, nullable=False)
    floor_price: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default={})
    embedding: Mapped[Any] = mapped_column(
        Vector(settings.database.vector_dimension), nullable=True
    )


class DealStatus(enum.Enum):
    """Status of a locked deal awaiting crypto payment."""

    PENDING = "PENDING"  # Payment not yet received
    PAID = "PAID"  # Payment confirmed on-chain
    EXPIRED = "EXPIRED"  # Deal expired before payment


class LockedDeal(Base):
    """
    Represents a negotiation deal locked behind a crypto payment.
    After payment is verified, the secret (reservation_code) is revealed.
    """

    __tablename__ = "locked_deals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String, nullable=False)
    final_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)  # "SOL" or "USDC"
    payment_memo: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    secret_content: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )  # Encrypted reservation code
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus), nullable=False, default=DealStatus.PENDING, index=True
    )
    buyer_did: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Payment verification fields (populated after confirmation)
    transaction_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    block_number: Mapped[str | None] = mapped_column(String, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
