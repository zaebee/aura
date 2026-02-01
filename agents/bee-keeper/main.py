import asyncio
import sys

import structlog

from src.config import KeeperSettings
from src.hive.core.aggregator import BeeAggregator
from src.hive.core.transformer import BeeTransformer
from src.hive.gateway.connector import BeeConnector
from src.hive.scribe.generator import BeeGenerator
from src.hive.metabolism import BeeMetabolism

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

    # 1. Initialize Nucleotides
    aggregator = BeeAggregator(settings=settings)
    transformer = BeeTransformer(settings=settings)
    connector = BeeConnector(settings=settings)
    generator = BeeGenerator(settings=settings)

    # 2. Initialize Metabolism
    metabolism = BeeMetabolism(
        aggregator=aggregator,
        transformer=transformer,
        connector=connector,
        generator=generator,
    )

    # 3. Execute Metabolic Cycle
    try:
        observation = await metabolism.execute()
        if observation.success:
            logger.info(
                "bee_keeper_agent_finished_successfully",
                comment_url=observation.github_comment_url,
            )
        else:
            logger.error("bee_keeper_agent_failed")
            sys.exit(1)
    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        if hasattr(connector, "close"):
            await connector.close()


if __name__ == "__main__":
    asyncio.run(main())
