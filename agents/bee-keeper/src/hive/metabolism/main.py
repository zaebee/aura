import time
import structlog
from aura_core.dna import AuditObservation, BeeContext

from src.hive.aggregator import BeeAggregator
from src.hive.connector import BeeConnector
from src.hive.generator import BeeGenerator
from src.hive.transformer import BeeTransformer

from .config import KeeperSettings

logger = structlog.get_logger(__name__)


class BeeMetabolism:
    """Orchestrates the ATCG flow for the bee.Keeper agent."""

    def __init__(self, settings: KeeperSettings) -> None:
        self.settings = settings
        self.aggregator = BeeAggregator(settings)
        self.transformer = BeeTransformer(settings)
        self.connector = BeeConnector(settings)
        self.generator = BeeGenerator(settings)

    async def execute(self, event_name: str = "scheduled_pulse") -> None:
        """Execute one complete metabolic cycle."""
        logger.info("bee_metabolism_started", trigger_event=event_name)
        start_time = time.time()

        # 1. Aggregator (A) - Senses the environment
        context: BeeContext = await self.aggregator.sense(event_name)

        # 2. Transformer (T) - Reasons and audits
        # Optimization: Skip LLM audit on scheduled heartbeats unless heresy is suspected?
        # Actually, let's honor the original skip logic if event is "schedule"
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
            report = await self.transformer.reflect(context)

        report.execution_time = time.time() - start_time

        # 3. Connector (C) - Interacts with the outer world (GitHub)
        observation = await self.connector.interact(report, context)

        # 4. Generator (G) - Updates records and chronicles
        await self.generator.generate(report, context, observation)

        logger.info(
            "bee_metabolism_completed",
            pure=report.is_pure,
            heresies=len(report.heresies),
            execution_time=f"{report.execution_time:.2f}s",
        )
