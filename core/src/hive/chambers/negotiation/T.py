import structlog
from aura_core import HiveContext, IntentAction
from aura_core.gen.aura.dna.v1 import ActionType

logger = structlog.get_logger(__name__)

async def calculate_strategy(context: HiveContext) -> float:
    """Pure Reasoning: Strategy logic (DSPy-like)."""
    # Logic: offer 95% of base price if it's above floor, otherwise base price
    base_price = context.item_data.get("base_price", 0.0)
    floor_price = context.item_data.get("floor_price", 0.0)
    suggested = base_price * 0.95
    return max(suggested, floor_price)

async def reason_about_margin(context: HiveContext, price: float) -> str:
    """Pure Reasoning: The <think> monologue."""
    bid = context.offer.bid_amount
    floor = context.item_data.get("floor_price", 0.0)
    return f"<think>Incoming bid is {bid}. Floor is {floor}. I decided on {price}.</think>"

async def think(context: HiveContext) -> IntentAction:
    """The Mind: Transforms context into intent."""
    logger.info("chamber_thinking", item_id=context.item_id)

    price = await calculate_strategy(context)
    thought = await reason_about_margin(context, price)

    # Simple decision logic
    if context.offer.bid_amount >= price:
        action = ActionType.ACTION_TYPE_ACCEPT
    else:
        action = ActionType.ACTION_TYPE_COUNTER

    return IntentAction(
        action=action,
        price=price,
        message=f"My best offer is {price}",
        thought=thought
    )
