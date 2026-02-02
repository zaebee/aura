import asyncio
import enum
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
from langchain_mistralai import MistralAIEmbeddings
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
from sqlalchemy.exc import SQLAlchemyError

from ...config import get_settings
from ...config.llm import get_raw_key

from aura_core.dna import HiveContext, NegotiationOffer

logger = structlog.get_logger(__name__)

# --- 1. Database (The Honeycomb Cells) ---

class Base(DeclarativeBase):
    pass

settings = get_settings()
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
    PENDING = "PENDING"
    PAID = "PAID"
    EXPIRED = "EXPIRED"

class LockedDeal(Base):
    __tablename__ = "locked_deals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    item_name: Mapped[str] = mapped_column(String, nullable=False)
    final_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    payment_memo: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    secret_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[DealStatus] = mapped_column(Enum(DealStatus), nullable=False, default=DealStatus.PENDING, index=True)
    buyer_did: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    transaction_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    block_number: Mapped[str | None] = mapped_column(String, nullable=True)
    from_address: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

def init_db() -> None:
    Base.metadata.create_all(bind=engine)

# --- 2. Embeddings (Semantic Sensory Organs) ---

def get_embeddings_model(model: str = "mistral-embed") -> MistralAIEmbeddings:
    return MistralAIEmbeddings(
        model=model,
        mistral_api_key=get_raw_key(settings.llm.api_key),
    )

def generate_embedding(text: str) -> list[float]:
    model = get_embeddings_model()
    return model.embed_query(text)

# --- 3. Monitoring (The Hive's Eyes) ---

class MetricsCache:
    """A simple in-memory cache for Prometheus metrics with a TTL."""
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, Any] = {}
        self._timestamp: float = 0.0

    def get(self, ignore_ttl: bool = False) -> dict[str, Any] | None:
        if not self._cache:
            return None
        if not ignore_ttl:
            age = time.time() - self._timestamp
            if age > self.ttl_seconds:
                return None
        return self._cache

    def set(self, metrics: dict[str, Any]) -> None:
        self._cache = metrics
        self._timestamp = time.time()

# --- 4. The Aggregator Bee ---

class HiveAggregator:
    """A - Aggregator: Consolidates database and system health signals."""
    def __init__(self) -> None:
        self.settings = get_settings()
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def _resolve_brain_path(self) -> str:
        search_paths = []
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.append(Path(self.settings.llm.compiled_program_path))
        search_paths.extend([Path("/app/src/aura_brain.json"), Path("./src/aura_brain.json"), Path(__file__).parent.parent / "aura_brain.json"])
        for path in search_paths:
            try:
                if path.exists() and path.is_file(): return str(path.absolute())
            except OSError: continue
        return "UNKNOWN"

    async def get_system_metrics(self) -> dict[str, Any]:
        """Queries Prometheus with self-healing (formerly monitor.py logic)."""
        cached = self._metrics_cache.get()
        if cached: return {**cached, "cached": True}

        cpu_query = 'avg(rate(container_cpu_usage_seconds_total{namespace="default"}[5m])) * 100'
        mem_query = 'avg(container_memory_working_set_bytes{namespace="default"}) / 1024 / 1024'

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                base_url = str(self.settings.server.prometheus_url).rstrip("/")
                responses = await asyncio.gather(
                    client.get(f"{base_url}/api/v1/query", params={"query": cpu_query}),
                    client.get(f"{base_url}/api/v1/query", params={"query": mem_query}),
                    return_exceptions=True
                )
                errors: list[str] = []
                cpu_usage, cpu_success = self._process_metric_response(responses[0], "cpu", errors)
                mem_usage, mem_success = self._process_metric_response(responses[1], "mem", errors)
                if not (cpu_success or mem_success):
                    raise httpx.ConnectError(f"All metric fetches failed: {', '.join(errors)}")
                metrics = {"status": "ok", "cpu_usage_percent": round(cpu_usage, 2), "memory_usage_mb": round(mem_usage, 2), "timestamp": datetime.now(UTC).isoformat(), "cached": False}
                if errors:
                    metrics["status"] = "PARTIAL"
                    metrics["warnings"] = errors
                self._metrics_cache.set(metrics)
                return metrics
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error("monitoring_failure", error=error_msg)
            cached = self._metrics_cache.get(ignore_ttl=True)
            if cached:
                return {
                    **cached,
                    "cached": True,
                    "warning": "stale_data",
                    "error": error_msg,
                }
            return {
                "status": "UNKNOWN",
                "cpu_usage_percent": 0.0,
                "memory_usage_mb": 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
                "error": error_msg,
            }

    def _process_metric_response(self, response, metric_name, errors):
        if isinstance(response, httpx.Response):
            try:
                response.raise_for_status()
                data = response.json()
                if data.get("status") == "success":
                    results = data.get("data", {}).get("result", [])
                    if results and len(results[0].get("value", [])) > 1:
                        return float(results[0]["value"][1]), True
                errors.append(f"{metric_name}_no_data")
            except Exception as e: errors.append(f"{metric_name}_parse_error")
        else: errors.append(f"{metric_name}_fetch_error")
        return 0.0, False

    async def perceive(self, signal: Any) -> HiveContext:
        item_id = signal.item_id
        request_id = getattr(signal, "request_id", "")
        offer = NegotiationOffer(bid_amount=signal.bid_amount, reputation=signal.agent.reputation_score, agent_did=signal.agent.did)
        item_data = {}
        try:
            def fetch():
                with SessionLocal() as session: return session.query(InventoryItem).filter_by(id=item_id).first()
            item = await asyncio.to_thread(fetch)
            if item: item_data = {"name": item.name, "base_price": item.base_price, "floor_price": item.floor_price, "meta": item.meta or {}}
        except Exception as e: logger.error("aggregator_db_error", error=str(e))

        system_health = await self.get_system_metrics()
        return HiveContext(item_id=item_id, offer=offer, item_data=item_data, system_health=system_health, request_id=request_id, metadata={"brain_path": self._resolve_brain_path()})
