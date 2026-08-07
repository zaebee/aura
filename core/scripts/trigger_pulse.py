import asyncio
import os
import uuid
from datetime import UTC, datetime

import nats
import structlog
from aura_core_gen.aura.core.v1 import ActionType, Event, NegotiationEvent

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


async def main():
    # Use AURA_NATS_URL or fallback to nats:4222
    nats_url = os.environ.get("AURA_NATS_URL", "nats://localhost:4222")
    topic = "aura.hive.events.negotiation_accept"

    # Create binary event
    event = Event(
        identifier=f"pulse-{uuid.uuid4().hex[:8]}",
        topic=topic,
        timestamp=datetime.now(UTC),
        negotiation=NegotiationEvent(
            item_identifier="item_1",
            action=ActionType.ACTION_TYPE_ACCEPT,
            price=100.0,
        ),
    )

    logger.info("connecting_to_nats", url=nats_url)
    try:
        nc = await nats.connect(nats_url)
        logger.info("publishing_to_nats", topic=topic)
        await nc.publish(topic, bytes(event))
        await nc.flush()
        await nc.close()
        logger.info("pulse_triggered_successfully")
    except Exception as e:
        logger.error("pulse_trigger_failed", error=str(e))


if __name__ == "__main__":
    asyncio.run(main())
