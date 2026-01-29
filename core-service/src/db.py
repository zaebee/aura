import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    LargeBinary,
    String,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

Base = declarative_base()
engine = create_engine(str(settings.database.url))
SessionLocal = sessionmaker(bind=engine)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    base_price = Column(Float, nullable=False)
    floor_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    meta = Column(JSONB, default={})
    embedding = Column(Vector(settings.database.vector_dimension))


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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(String, nullable=False, index=True)
    item_name = Column(String, nullable=False)
    final_price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)  # "SOL" or "USDC"
    payment_memo = Column(String, nullable=False, unique=True, index=True)
    secret_content = Column(LargeBinary, nullable=False)  # Encrypted reservation code
    status = Column(
        Enum(DealStatus), nullable=False, default=DealStatus.PENDING, index=True
    )
    buyer_did = Column(String, nullable=True, index=True)

    # Payment verification fields (populated after confirmation)
    transaction_hash = Column(String, nullable=True)
    block_number = Column(String, nullable=True)
    from_address = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    paid_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


def init_db():
    Base.metadata.create_all(bind=engine)
