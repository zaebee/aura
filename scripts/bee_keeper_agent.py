import asyncio
import sys

import structlog

from scripts.bee_keeper.aggregator import BeeAggregator
from scripts.bee_keeper.connector import BeeConnector
from scripts.bee_keeper.generator import BeeGenerator
from scripts.bee_keeper.metabolism import BeeMetabolism
from scripts.bee_keeper.transformer import BeeTransformer

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

    # 1. Initialize Nucleotides
    aggregator = BeeAggregator()
    transformer = BeeTransformer()
    connector = BeeConnector()
    generator = BeeGenerator()

    # 2. Initialize Metabolism
    metabolism = BeeMetabolism(
        aggregator=aggregator,
        transformer=transformer,
        connector=connector,
        generator=generator
    )

    # 3. Execute Metabolic Cycle
    try:
        observation = await metabolism.execute()
        if observation.success:
            logger.info("bee_keeper_agent_finished_successfully", comment_url=observation.github_comment_url)
        else:
            logger.error("bee_keeper_agent_failed")
            sys.exit(1)
    except Exception as e:
        logger.error("bee_keeper_agent_critical_error", error=str(e), exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
