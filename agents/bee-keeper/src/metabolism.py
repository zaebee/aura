import structlog

from src.dna import (
    BeeAggregator,
    BeeConnector,
    BeeGenerator,
    BeeObservation,
    BeeTransformer,
    PurityReport,
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
        import time

        logger.info("bee_metabolism_started")
        start_time = time.time()

        # 1. Aggregator (A) - Perceive/Sense
        context = await self.aggregator.perceive()

        # 2. Transformer (T) - Think/Reason
        if context.event_name == "schedule":
            logger.info("scheduled_heartbeat_detected_skipping_llm_audit")
            report = PurityReport(
                is_pure=True,
                narrative="The Keeper performs a routine inspection. The Hive's pulse is steady.",
                reasoning="Scheduled heartbeat run. LLM audit skipped to save honey.",
                metadata={"heartbeat": True},
            )
        else:
            report = await self.transformer.think(context)

        report.execution_time = time.time() - start_time

        # 3. Connector (C) - Act/Output
        observation = await self.connector.act(report, context)

        # 4. Generator (G) - Generate/Chronicle
        await self.generator.generate(report, context, observation)

        logger.info(
            "bee_metabolism_completed",
            is_pure=report.is_pure,
            heresies_count=len(report.heresies)
        )

        return observation
