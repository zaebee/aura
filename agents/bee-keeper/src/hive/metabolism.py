import structlog

from src.config import KeeperSettings
from src.hive.core.aggregator import BeeAggregator
from src.hive.gateway.connector import BeeConnector
from src.hive.core.transformer import BeeTransformer
from src.hive.dna import BeeContext
from src.hive.scribe.generator import BeeGenerator

logger = structlog.get_logger(__name__)


class MetabolicLoop:
    """The ATCG cycle for the bee.Keeper agent."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.aggregator = BeeAggregator(settings)
        self.transformer = BeeTransformer(settings)
        self.connector = BeeConnector(settings)
        self.generator = BeeGenerator(settings)

    async def pulse(self, event_name: str = "scheduled_pulse") -> None:
        """Execute one complete metabolic cycle."""
        logger.info("metabolic_pulse_started", trigger_event=event_name)

        # 1. Aggregator (A) - Senses the environment
        context: BeeContext = await self.aggregator.sense(event_name)

        # 2. Transformer (T) - Reasons and audits
        # Note: T now performs deterministic regex audit + reflective LLM analysis
        report = await self.transformer.reflect(context)

        # 3. Connector (C) - Interacts with the outer world (GitHub)
        observation = await self.connector.interact(report, context)

        # 4. Generator (G) - Updates records and chronicles
        await self.generator.generate(report, context, observation)

        logger.info(
            "metabolic_pulse_completed",
            pure=report.is_pure,
            heresies=len(report.heresies),
        )
