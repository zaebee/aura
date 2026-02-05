from typing import Any
import structlog
from aura_core import HiveContext, NegotiationOffer, SystemVitals

logger = structlog.get_logger(__name__)

async def get_item_from_db(item_id: str) -> dict[str, Any]:
    """Pure READ: SQL select simulation."""
    logger.info("chamber_read_db", item_id=item_id)
    # Simulation of database retrieval
    return {
        "id": item_id,
        "name": "Atomic Core",
        "base_price": 100.0,
        "floor_price": 85.0
    }

async def get_market_vitals() -> SystemVitals:
    """Pure READ: Prometheus query simulation."""
    logger.info("chamber_read_vitals")
    return SystemVitals(status="healthy", cpu_usage_percent=15.0)

async def perceive(signal: Any) -> HiveContext:
    """Consolidate the past into a context."""
    item_id = getattr(signal, "item_id", "default_item")
    bid = getattr(signal, "bid_amount", 0.0)

    item_data = await get_item_from_db(item_id)
    vitals = await get_market_vitals()

    return HiveContext(
        item_id=item_id,
        offer=NegotiationOffer(bid_amount=bid),
        item_data=item_data,
        system_health=vitals
    )
