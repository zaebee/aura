import subprocess  # nosec
from datetime import UTC, datetime

import structlog

from config import EvolverSettings
from .aggregator import EvolverAggregator
from .connector import EvolverConnector
from .generator import EvolverGenerator
from .models import EvolverObservation, EvolutionPlan
from .transformer import EvolverTransformer

logger = structlog.get_logger(__name__)


class EvolverMetabolism:
    """Orchestrates the ATCG flow for the bee.Evolver agent."""

    def __init__(self, settings: EvolverSettings) -> None:
        self.settings = settings
        self.aggregator = EvolverAggregator(settings)
        self.transformer = EvolverTransformer(settings)
        self.generator = EvolverGenerator(settings)
        self.connector = EvolverConnector(settings)

    async def execute(self) -> EvolverObservation:
        """Run one complete evolutionary cycle."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        logger.info("evolver_metabolism_started", timestamp=timestamp)

        # Configure git identity for CI
        self._configure_git()

        # 1. A — Aggregate: sense the Hive
        context = await self.aggregator.perceive()

        # 2. T — Transform: produce improvement plan
        plan: EvolutionPlan = await self.transformer.think(context)

        branch = ""
        apply_errors: list[str] = []

        if not plan.hive_is_optimal and plan.improvements:
            patchable = [
                i for i in plan.improvements if i.type in ("code", "prompt", "doc") and i.patch
            ]

            if patchable:
                # 3. G — Generate: apply patches and push branch
                try:
                    branch = self.generator.prepare_branch(timestamp)
                    apply_errors = self.generator.apply_improvements(plan)
                    pushed = self.generator.commit_and_push(branch, timestamp)
                    if not pushed:
                        apply_errors.append("Failed to push branch to origin.")
                        branch = ""
                except Exception as e:
                    logger.error("generator_failed", error=str(e))
                    apply_errors.append(f"Generator error: {e}")
                    branch = ""
            else:
                logger.info(
                    "no_patchable_improvements_skipping_branch",
                    total=len(plan.improvements),
                )

        # 4. C — Connect: open Issues/PR + Telegram pulse
        observation = await self.connector.act(
            plan=plan,
            branch=branch,
            timestamp=timestamp,
            apply_errors=apply_errors,
        )

        logger.info(
            "evolver_metabolism_completed",
            improvements=len(plan.improvements),
            pr_url=observation.pr_url,
            telegram_sent=observation.telegram_sent,
            errors=len(observation.errors),
        )
        return observation

    def _configure_git(self) -> None:
        """Set git identity for CI commits."""
        try:
            subprocess.run(  # nosec
                ["git", "config", "--global", "user.name", "bee.Evolver"],
                check=False,
                capture_output=True,
            )
            subprocess.run(  # nosec
                ["git", "config", "--global", "user.email", "evolver@aura.hive"],
                check=False,
                capture_output=True,
            )
        except Exception as e:
            logger.warning("git_config_failed", error=str(e))
