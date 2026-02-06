from typing import Any

import structlog
from aura_core import HiveContext, NegotiationOffer, SkillRegistry, SystemVitals

logger = structlog.get_logger(__name__)

DEFAULT_ITEM_ID = "default_item"


async def perceive(signal: Any, registry: SkillRegistry) -> HiveContext:
    """
    The Past: Consolidates signals into a context using real Proteins.
    - Uses 'persistence' Skill (Storage)
    - Uses 'telemetry' Skill (Monitor)
    """
    item_id = getattr(signal, "item_id", DEFAULT_ITEM_ID)
    bid = getattr(signal, "bid_amount", 0.0)
    request_id = getattr(signal, "request_id", "")

    logger.info("chamber_perceive", item_id=item_id, bid=bid)

    # 1. Fetch Item Data from Persistence Protein (Storage)
    item_data = {}
    item_obs = await registry.execute("persistence", "read_item", {"item_id": item_id})
    if item_obs.success:
        item_data = item_obs.data
    else:
        logger.warning("chamber_persistence_read_failed", error=item_obs.error)

    # 2. Fetch System Vitals from Telemetry Protein (Monitor)
    vitals = SystemVitals(status="unknown")
    vitals_obs = await registry.execute("telemetry", "get_vitals", {})
    if vitals_obs.success:
        vitals = SystemVitals(**vitals_obs.data)
    else:
        logger.warning("chamber_telemetry_read_failed", error=vitals_obs.error)

    return HiveContext(
        item_id=item_id,
        offer=NegotiationOffer(bid_amount=bid),
        item_data=item_data,
        system_health=vitals,
        request_id=request_id,
    )
