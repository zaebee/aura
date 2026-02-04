import time

import structlog

from config import KeeperSettings
from aura_core import (
    AuditObservation,
    BeeContext,
    BeeObservation,
)
from .aggregator import BeeAggregator
from .connector import BeeConnector
from .generator import BeeGenerator
from .transformer import BeeTransformer

logger = structlog.get_logger(__name__)


class BeeMetabolism:
    """Orchestrates the ATCG flow for the bee.Keeper agent."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.aggregator: BeeAggregator = BeeAggregator(settings)
        self.transformer: BeeTransformer = BeeTransformer(settings)
        self.connector: BeeConnector = BeeConnector(settings)
        self.generator: BeeGenerator = BeeGenerator(settings)

    async def execute(self, event_name: str = "scheduled_pulse") -> None:
        """Execute one complete metabolic cycle."""
        logger.info("bee_metabolism_started", trigger_event=event_name)
        start_time = time.time()

        # 1. Aggregator (A) - Senses the environment
        context: BeeContext = await self.aggregator.perceive(
            None, event_name=event_name
        )

        # 2. Transformer (T) - Reasons and audits
        if event_name == "schedule":
            logger.info("scheduled_heartbeat_detected_skipping_llm_audit")
            report = AuditObservation(
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
        observation: BeeObservation = await self.connector.act(report, context=context)

        # Enrich observation with context and report for the Generator
        observation.context = context
        observation.report = report

        # 4. Generator (G) - Updates records and chronicles
        await self.generator.pulse(observation)

        logger.info(
            "bee_metabolism_completed",
            pure=report.is_pure,
            heresies=len(report.heresies),
            execution_time=f"{report.execution_time:.2f}s",
        )
