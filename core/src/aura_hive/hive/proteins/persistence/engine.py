import enum
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import redis.asyncio as redis
import structlog
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


class SanctifiedWallet(Base):
    """Immune Registry: wallets approved for on-chain transactions."""

    __tablename__ = "sanctified_wallets"

    wallet_address: Mapped[str] = mapped_column(String, primary_key=True)
    asset_domain: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )


class MetabolicCost(Base):
    __tablename__ = "metabolic_costs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    network: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    transaction_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )


class DecisionReceiptRecord(Base):
    """
    The auditor's copy of a decision receipt.

    The log line was the only store, and it lives in a Loki with a short
    retention — so a dispute arriving a month after the decision found nothing.
    This table is what makes the corpus outlive the stream; the log line stays
    as a second, independent path.

    Nothing here is a price or a premise. Every receipt field is a digest, an
    identifier, an enum, a timestamp or signature metadata, which is why the
    whole document can be stored without becoming a new place the floor lives.
    """

    __tablename__ = "decision_receipts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # What the counterparty cites. The lookup key.
    dispute_token: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    # What the signature binds — the auditor's other way in.
    decision_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # The session, for reassembling a whole negotiation.
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # The receipt's own timestamp, kept as the string it carries rather than
    # parsed into a DateTime, so the column holds what was signed instead of a
    # reconstruction of it.
    issued_at: Mapped[str] = mapped_column(String, nullable=False)
    # The whole document, exactly as the log line carries it.
    receipt: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # When the row was written — deliberately separate from `issued_at`, so a
    # divergence between deciding and recording is visible rather than hidden.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )


logger = structlog.get_logger(__name__)


def negotiation_history_key(agent_did: str, item_id: str) -> str:
    """
    Stable key for one (agent, item) conversation.

    Hashed rather than interpolated: a DID or item id may contain the delimiter,
    so `a:b` + `c` and `a` + `b:c` would otherwise collide, and either can be
    long enough to make an awkward key. The plain values are stored inside each
    turn, so a key can still be traced back.
    """
    digest = hashlib.sha256(f"{agent_did}\x00{item_id}".encode()).hexdigest()
    return f"negotiation:history:{digest[:32]}"


class RedisCache:
    """Redis-based caching and excited state storage."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def set_excited_state(
        self, deal_id: str, deal_data: dict, ttl: int = 3600
    ) -> None:
        """Store deal in 'Excited' state (unpaid, Redis)."""
        key = f"deal:excited:{deal_id}"
        # Convert bytes to hex for JSON serialization if needed
        # But deal_data might have bytes
        serializable_data = {}
        for k, v in deal_data.items():
            if isinstance(v, bytes):
                serializable_data[k] = v.hex()
            elif isinstance(v, datetime):
                serializable_data[k] = v.isoformat()
            elif isinstance(v, uuid.UUID):
                serializable_data[k] = str(v)
            else:
                serializable_data[k] = v

        await self.redis.set(key, json.dumps(serializable_data), ex=ttl)

    async def get_excited_state(self, deal_id: str) -> dict[str, Any] | None:
        """Retrieve deal from 'Excited' state."""
        key = f"deal:excited:{deal_id}"
        data = await self.redis.get(key)
        if data:
            return cast(dict[str, Any], json.loads(data))
        return None

    # ------------------------------------------------------------------
    # Negotiation history
    #
    # Turns are grouped by (agent_did, item_id) because the wire protocol
    # carries no conversation identifier: NegotiateRequest has request_id,
    # item_id, bid_amount, currency_code and agent, and session_token is
    # derived per request. Two independent negotiations by the same agent over
    # the same item therefore merge into one history; the TTL bounds how long.
    # Fixing that properly means adding a conversation_id to the proto.
    # ------------------------------------------------------------------

    async def append_negotiation_turn(
        self,
        agent_did: str,
        item_id: str,
        turn: dict[str, Any],
        ttl: int = 3600,
        cap: int = 20,
    ) -> None:
        """
        Append one turn, keeping the most recent `cap`.

        A Redis list rather than a JSON blob: RPUSH is atomic, so concurrent
        turns cannot lose each other the way read-modify-write would, and LTRIM
        bounds the prompt this history will end up in.
        """
        key = negotiation_history_key(agent_did, item_id)
        pipe = self.redis.pipeline()
        pipe.rpush(key, json.dumps(turn))
        pipe.ltrim(key, -cap, -1)
        pipe.expire(key, ttl)
        await pipe.execute()

    async def get_negotiation_history(
        self, agent_did: str, item_id: str
    ) -> list[dict[str, Any]]:
        """Turns oldest first. A malformed entry is skipped, never fatal."""
        key = negotiation_history_key(agent_did, item_id)
        # redis-py types lrange as sync-or-async; the asyncio client always
        # returns an awaitable.
        raw = cast(list[Any], await self.redis.lrange(key, 0, -1))  # type: ignore[misc]
        history: list[dict[str, Any]] = []
        for entry in raw:
            try:
                history.append(json.loads(entry))
            except (TypeError, ValueError):
                logger.warning("negotiation_history_entry_unreadable", key=key)
        return history

    async def delete_excited_state(self, deal_id: str) -> None:
        """Remove deal from 'Excited' state."""
        key = f"deal:excited:{deal_id}"
        await self.redis.delete(key)
