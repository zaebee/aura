import asyncio
import sys

import structlog

from src.config import KeeperSettings
from src.hive.metabolism import MetabolicLoop

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

    loop = None
    try:
        # 1. Initialize Metabolism
        loop = MetabolicLoop(settings)

        # 1.5 Sanity Check: Test Brain Connectivity
        await loop.aggregator.test_brain_connectivity()

        # 2. Execute Metabolic Pulse
        # KeeperSettings already maps GITHUB_EVENT_NAME
        event_name = settings.github_event_name
        await loop.pulse(event_name=event_name)
        logger.info("bee_keeper_agent_finished_successfully")
    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if loop and loop.connector:
            await loop.connector.close()


if __name__ == "__main__":
    asyncio.run(main())
