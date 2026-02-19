import asyncio
import sys

import structlog

from config import KeeperSettings
from hive.metabolism import BeeMetabolism

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


import nats
import nats.errors

async def main() -> None:
    logger.info("bee_keeper_agent_starting")

    # 0. Load Settings
    settings = KeeperSettings()

    metabolism = None
    try:
        # 1. Initialize Metabolism
        metabolism = BeeMetabolism(settings)

        # 1.5 Sanity Check: Test Brain Connectivity
        if not await metabolism.aggregator.test_brain_connectivity():
            logger.error(
                "Brain connectivity test failed. Check AURA_LLM__API_KEY."
            )
            # We don't exit here to allow for intermittent connectivity
            # sys.exit(1)

        # 2. Connect to NATS Bloodstream
        nc = await nats.connect(settings.nats_url)
        logger.info("connected_to_nats", url=settings.nats_url)

        # 3. Subscribe to Error Events
        error_subject = "aura.hive.events.error"
        sub = await nc.subscribe(error_subject)
        logger.info("subscribed_to_errors", subject=error_subject)

        # 4. Metabolic Loop (Continuous)
        async for msg in sub.messages:
            try:
                logger.info("error_signal_detected", subject=msg.subject)
                # Execute one complete metabolic cycle for each error
                await metabolism.execute(signal=msg.data, event_name="error_diagnosis")
            except Exception as e:
                logger.error("cycle_failure", error=str(e))

    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if metabolism and metabolism.connector:
            await metabolism.connector.close()


if __name__ == "__main__":
    asyncio.run(main())
