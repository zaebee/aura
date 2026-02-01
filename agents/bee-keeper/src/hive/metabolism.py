import time
import structlog

from aura_core.dna import (
    BeeAggregator,
    BeeConnector,
    BeeContext,
    BeeGenerator,
    BeeObservation,
    BeeTransformer,
    PurityReport,
)

logger = structlog.get_logger(__name__)


class BeeMetabolism:
    """Orchestrates the ATCG flow for the bee.Keeper agent."""

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
        """Execute one complete metabolic cycle."""
        logger.info("bee_metabolism_started")
        start_time = time.time()

        # 1. Aggregator (A) - Senses the environment
        context: BeeContext = await self.aggregator.perceive()

        # 2. Transformer (T) - Reasons and audits
        if context.event_name == "schedule":
            logger.info("scheduled_heartbeat_detected_skipping_llm_audit")
            report = PurityReport(
                is_pure=True,
                narrative="The Keeper performs a routine inspection. The Hive's pulse is steady.",
                reasoning="Scheduled heartbeat run. LLM audit skipped to save honey.",
                metadata={"heartbeat": True},
            )
        else:
            # T now performs deterministic regex audit + reflective LLM analysis
            report = await self.transformer.think(context)

        report.execution_time = time.time() - start_time

        # 3. Connector (C) - Interacts with the outer world (GitHub)
        observation = await self.connector.act(report, context)

        # 4. Generator (G) - Updates records and chronicles
        await self.generator.generate(report, context, observation)

        logger.info(
            "bee_metabolism_completed",
            pure=report.is_pure,
            heresies=len(report.heresies),
            execution_time=f"{report.execution_time:.2f}s",
        )
        return observation
