import asyncio
from pathlib import Path
from typing import Any

import structlog
from aura_core import Aggregator, HiveContext, NegotiationOffer, SystemVitals

from config import get_settings

from .db import InventoryItem, SessionLocal
from .vitals import MetricsCache, fetch_vitals

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, HiveContext]):
    """A - Aggregator: Consolidates database and system health signals."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._metrics_cache = MetricsCache(ttl_seconds=30)

    def _resolve_brain_path(self) -> str:
        search_paths = []
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.append(Path(self.settings.llm.compiled_program_path))
        search_paths.extend(
            [
                Path("/app/src/aura_brain.json"),
                Path("./src/aura_brain.json"),
                Path(__file__).parent.parent / "aura_brain.json",
            ]
        )
        for path in search_paths:
            try:
                if path.exists() and path.is_file():
                    return str(path.absolute())
            except OSError:
                continue
        return "UNKNOWN"

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics)."""
        return await fetch_vitals(self._metrics_cache, self.settings)

    async def get_system_metrics(self) -> dict[str, Any]:
        """Backward compatibility for legacy status calls."""
        vitals = await self.get_vitals()
        return vitals.model_dump()

    async def perceive(self, signal: Any, **kwargs: Any) -> HiveContext:
        item_id = signal.item_id
        request_id = getattr(signal, "request_id", "")
        offer = NegotiationOffer(
            bid_amount=signal.bid_amount,
            reputation=signal.agent.reputation_score,
            agent_did=signal.agent.did,
        )
        item_data = {}
        try:

            def fetch() -> InventoryItem | None:
                with SessionLocal() as session:
                    return session.query(InventoryItem).filter_by(id=item_id).first()

            item = await asyncio.to_thread(fetch)
            if item:
                item_data = {
                    "name": item.name,
                    "base_price": item.base_price,
                    "floor_price": item.floor_price,
                    "meta": item.meta or {},
                }
        except Exception as e:
            logger.error("aggregator_db_error", error=str(e))

        return HiveContext(
            item_id=item_id,
            offer=offer,
            item_data=item_data,
            # system_health will be automatically injected by MetabolicLoop
            request_id=request_id,
            metadata={"brain_path": self._resolve_brain_path()},
        )
