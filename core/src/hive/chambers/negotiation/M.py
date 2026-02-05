import structlog
from aura_core import HiveContext, IntentAction
from aura_core.gen.aura.dna.v1 import ActionType

logger = structlog.get_logger(__name__)

async def filter_in(context: HiveContext) -> HiveContext:
    """The Firmament: Sanitize inbound signals."""
    logger.info("chamber_membrane_in")
    # Sanitize: ensure bid_amount is non-negative
    if context.offer.bid_amount < 0:
        logger.warn("chamber_membrane_negative_bid_corrected")
        context.offer.bid_amount = 0.0
    return context

async def filter_out(intent: IntentAction, context: HiveContext) -> IntentAction:
    """The Firmament: Deterministic Guardrails."""
    logger.info("chamber_membrane_out")

    # Logic: If price is below floor price, override with floor price
    floor_price = context.item_data.get("floor_price", 0.0)

    if intent.price < floor_price:
        logger.info("chamber_membrane_floor_violation_override", intent_price=intent.price, floor_price=floor_price)
        intent.price = floor_price
        intent.action = ActionType.ACTION_TYPE_COUNTER
        intent.message = f"Our policy does not allow offers below {floor_price}."
        intent.thought += " [Membrane: Floor Price Override applied]"

    return intent
