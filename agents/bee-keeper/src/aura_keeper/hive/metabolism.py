import time
from datetime import UTC, datetime

import structlog

from aura_keeper.config import KeeperSettings
from aura_core_gen.aura.core.v1 import (
    AuditObservation,
)
from .records import MetabolicRecord, Outcome
from .aggregator import BeeAggregator
from .connector import BeeConnector, BeeObservation
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
        # monotonic, not time(): start_time is only ever used to compute
        # durations, and a wall clock can be stepped backwards by NTP.
        start_time = time.monotonic()
        cycle_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        outcome: Outcome = "success"
        # The cycle boundary, not think(): scheduled runs skip the LLM entirely
        # and would otherwise carry the previous cycle's totals into their record.
        self.transformer.reset_usage()

        try:
            # 1. Aggregator (A) - Senses the environment
            try:
                context = await self.aggregator.perceive(None, event_name=event_name)
            except Exception:
                outcome = "aggregator_error"
                raise

            # 2. Transformer (T) - Reasons and audits
            if event_name == "schedule":
                logger.info("scheduled_heartbeat_detected_skipping_llm_audit")
                report = AuditObservation(
                    is_pure=True,
                    narrative="The Keeper performs a routine inspection. The Hive's pulse is steady.",
                    reasoning="Scheduled heartbeat run. LLM audit skipped to save honey.",
                )
            else:
                # T now performs deterministic regex audit + reflective LLM analysis
                try:
                    report = await self.transformer.think(context)
                except Exception:
                    outcome = "llm_error"
                    raise

            report.execution_time = float(time.monotonic() - start_time)

            # 3. Connector (C) - Interacts with the outer world (GitHub)
            try:
                observation: BeeObservation = await self.connector.act(
                    report, context=context
                )
            except Exception:
                outcome = "connector_error"
                raise

            # Enrich observation with context and report for the Generator
            observation.context = context
            observation.report = report

            # 4. Generator (G) - Updates records and chronicles
            try:
                await self.generator.pulse(observation)
            except Exception:
                outcome = "generator_error"
                raise

            logger.info(
                "bee_metabolism_completed",
                pure=report.is_pure,
                heresies=len(report.heresies),
                execution_time=f"{report.execution_time:.2f}s",
            )
        except Exception:
            # Every stage above labels its own failure. Anything reaching here
            # failed outside them, and must not be mislabelled as one of them.
            if outcome == "success":
                outcome = "unknown_error"
            raise
        finally:
            totals = self.transformer.usage_totals
            self.connector.write_metabolic_record(
                MetabolicRecord(
                    ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    bee="keeper",
                    cycle_id=cycle_id,
                    git_sha=self.settings.git_sha,
                    model=totals["model"],
                    llm_calls=int(totals["llm_calls"]),
                    prompt_tokens=totals["prompt_tokens"],
                    completion_tokens=totals["completion_tokens"],
                    usd=totals["usd"],
                    wall_clock_s=round(time.monotonic() - start_time, 3),
                    outcome=outcome,
                    dry_run=False,
                )
            )
