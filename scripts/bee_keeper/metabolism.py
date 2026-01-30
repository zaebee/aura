import structlog

from src.hive.dna import (
    BeeAggregator,
    BeeConnector,
    BeeGenerator,
    BeeObservation,
    BeeTransformer,
)

logger = structlog.get_logger(__name__)

class BeeMetabolism:
    """
    Orchestrates the ATCG flow for the BeeKeeper agent:
    A (Aggregator) -> T (Transformer) -> C (Connector) -> G (Generator)
    """

    def __init__(
        self,
        aggregator: BeeAggregator,
        transformer: BeeTransformer,
        connector: BeeConnector,
        generator: BeeGenerator,
    ):
        self.aggregator = aggregator
        self.transformer = transformer
        self.connector = connector
        self.generator = generator

    async def execute(self) -> BeeObservation:
        """Execute one full metabolic cycle of the BeeKeeper."""
        logger.info("bee_metabolism_started")

        # 1. Aggregator (A) - Perceive/Sense
        context = await self.aggregator.perceive()

        # 2. Transformer (T) - Think/Reason
        report = await self.transformer.think(context)

        # 3. Connector (C) - Act/Output
        observation = await self.connector.act(report, context)

        # 4. Generator (G) - Generate/Chronicle
        await self.generator.generate(report, context)

        logger.info(
            "bee_metabolism_completed",
            is_pure=report.is_pure,
            heresies_count=len(report.heresies)
        )

        return observation
