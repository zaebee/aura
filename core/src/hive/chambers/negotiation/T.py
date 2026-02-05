from typing import Any, cast

import structlog
from aura_core import HiveContext, IntentAction, SkillRegistry, map_action
from aura_core.gen.aura.dna.v1 import ActionType

logger = structlog.get_logger(__name__)


async def think(context: HiveContext, registry: SkillRegistry) -> IntentAction:
    """
    The Mind: Pure reasoning wrapper around the Reasoning Protein.
    - Uses 'reasoning' Skill (encapsulates DSPy and brain)
    """
    logger.info("chamber_thinking", item_id=context.item_id)

    # Delegate reasoning to the Reasoning Protein
    obs = await registry.execute(
        "reasoning",
        "negotiate",
        {
            "bid": context.offer.bid_amount,
            "context": {
                "base_price": context.item_data.get("base_price", 0.0),
                "floor_price": context.item_data.get("floor_price", 0.0),
                "reputation": context.offer.reputation,
            },
            "history": [],
        },
    )

    if not obs.success:
        logger.error("chamber_reasoning_failed", error=obs.error)
        return IntentAction(
            action=cast(Any, ActionType.ACTION_TYPE_ERROR),
            price=0.0,
            message="Reasoning engine unavailable.",
            thought=f"<think>Error: {obs.error}</think>",
        )

    result = obs.data

    return IntentAction(
        action=cast(Any, map_action(result.get("action"))),
        price=float(result["price"]),
        message=result["message"],
        thought=result.get("thought", ""),
        metadata=result.get("metadata", {}),
    )
