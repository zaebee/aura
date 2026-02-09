import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    LargeBinary,
    String,
)

if TYPE_CHECKING:
    pass
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)
import redis.asyncio as redis
import json

# DNA Rule: Proteins must not import global settings.
# Models will be initialized during Skill.initialize()


# 1. Implementation Details: SQLAlchemy Setup
class Base(DeclarativeBase):
    pass


# 2. Implementation Details: Database Models
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
    embedding: Mapped[Any] = mapped_column(Vector, nullable=True)


class DealStatus(enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    EXPIRED = "EXPIRED"


class LockedDeal(Base):
    __tablename__ = "locked_deals"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String, nullable=False)
    final_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    payment_memo: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    secret_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus), nullable=False, default=DealStatus.PENDING, index=True
    )
    buyer_did: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    transaction_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    block_number: Mapped[str | None] = mapped_column(String, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String, nullable=True)
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


class RedisCache:
    """Redis technical implementation for caching."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve a JSON-serialized value from Redis."""
        data = await self.redis.get(key)
        if data:
            return cast(dict[str, Any], json.loads(data))
        return None

    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Store a value in Redis as JSON with TTL."""
        data = json.dumps(value)
        return await self.redis.set(key, data, ex=ttl)
