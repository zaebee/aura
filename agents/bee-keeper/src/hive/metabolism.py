import time
import structlog
from typing import Any

from config import KeeperSettings
from .aggregator import BeeAggregator
from .connector import BeeConnector
from .transformer import BeeTransformer
from aura_core import BeeContext, AuditObservation, BeeObservation, Aggregator, Transformer, Connector, Generator
from .generator import BeeGenerator

logger = structlog.get_logger(__name__)


class BeeMetabolism:
    """Orchestrates the ATCG flow for the bee.Keeper agent."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.aggregator: Aggregator[Any, BeeContext] = BeeAggregator(settings)
        self.transformer: Transformer[BeeContext, AuditObservation] = BeeTransformer(settings)
        self.connector: Connector[AuditObservation, BeeObservation] = BeeConnector(settings)
        self.generator: Generator[BeeObservation, Any] = BeeGenerator(settings)

    async def execute(self, event_name: str = "scheduled_pulse") -> None:
        """Execute one complete metabolic cycle."""
        logger.info("bee_metabolism_started", trigger_event=event_name)
        start_time = time.time()

        # 1. Aggregator (A) - Senses the environment
        context: BeeContext = await self.aggregator.perceive(None, event_name=event_name)

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

        # 4. Generator (G) - Updates records and chronicles
        # We still use the specialized generate method for bee-keeper as it needs more context
        if hasattr(self.generator, "generate"):
            await self.generator.generate(report, context, observation)
        else:
            await self.generator.pulse(observation)

        logger.info(
            "bee_metabolism_completed",
            pure=report.is_pure,
            heresies=len(report.heresies),
            execution_time=f"{report.execution_time:.2f}s",
        )
