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
                "Brain connectivity test failed for both primary and fallback models. Exiting."
            )
            sys.exit(1)

        # 2. Execute Metabolic Pulse
        # KeeperSettings already maps GITHUB_EVENT_NAME
        event_name = settings.github_event_name
        await metabolism.execute(event_name=event_name)
        logger.info("bee_keeper_agent_finished_successfully")
    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if metabolism and metabolism.connector:
            await metabolism.connector.close()


if __name__ == "__main__":
    asyncio.run(main())
