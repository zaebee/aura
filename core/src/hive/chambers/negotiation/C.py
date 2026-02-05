import structlog
from aura_core import IntentAction, Observation

logger = structlog.get_logger(__name__)

async def save_deal_to_db(action: IntentAction):
    """Pure WRITE: SQL insert simulation."""
    logger.info("chamber_write_db", price=action.price)

async def execute_solana_transfer(action: IntentAction):
    """Pure ACTION: Blockchain I/O simulation."""
    logger.info("chamber_solana_transfer", price=action.price)

async def send_grpc_response(action: IntentAction):
    """Pure ACTION: Communication."""
    logger.info("chamber_grpc_response", action=str(action.action))

async def act(action: IntentAction) -> Observation:
    """The Motor: Executes the safe action."""
    await save_deal_to_db(action)

    # Example logic: Only transfer if it's high value for demo
    if action.price > 50:
        await execute_solana_transfer(action)

    await send_grpc_response(action)

    return Observation(
        success=True,
        event_type="negotiation_processed",
        metadata={"price": action.price}
    )
