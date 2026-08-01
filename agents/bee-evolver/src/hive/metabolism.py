import subprocess  # nosec
import time
from datetime import UTC, datetime

import structlog

from config import EvolverSettings
from .aggregator import EvolverAggregator
from .connector import EvolverConnector
from .generator import EvolverGenerator
from .models import EvolverObservation, EvolutionPlan
from .records import MetabolicRecord
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

        started = time.monotonic()
        plan = EvolutionPlan()
        outcome = "success"
        proposals = 0
        applied = 0

        try:
            # Configure git identity for CI
            self._configure_git()

            # 1. A — Aggregate: sense the Hive
            context = await self.aggregator.perceive()

            # 2. T — Transform: produce improvement plan
            plan = await self.transformer.think(context)
            if plan.llm_failed:
                outcome = "llm_error"
            proposals = len(plan.improvements)

            branch = ""
            apply_errors: list[str] = []

            if not plan.hive_is_optimal and plan.improvements:
                patchable = [
                    i
                    for i in plan.improvements
                    if i.type in ("code", "prompt", "doc") and i.patch
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
                    if apply_errors and outcome == "success":
                        outcome = "generator_error"
                    applied = max(len(patchable) - len(apply_errors), 0)
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
        except Exception:
            if outcome == "success":
                outcome = "llm_error"
            raise
        finally:
            self.connector.write_metabolic_record(
                MetabolicRecord(
                    ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    bee="evolver",
                    cycle_id=timestamp,
                    git_sha=self.settings.git_sha,
                    model=plan.model_used,
                    llm_calls=plan.llm_calls,
                    prompt_tokens=plan.prompt_tokens,
                    completion_tokens=plan.completion_tokens,
                    usd=plan.usd,
                    wall_clock_s=round(time.monotonic() - started, 3),
                    outcome=outcome,
                    dry_run=self.settings.dry_run,
                    proposals=proposals,
                    applied=applied,
                )
            )

    def _configure_git(self) -> None:
        """Set git identity scoped to the current repository (not global)."""
        from .utils import find_hive_root
        root = str(find_hive_root())
        try:
            subprocess.run(  # nosec
                ["git", "config", "user.name", "bee.Evolver"],
                check=True,
                capture_output=True,
                cwd=root,
            )
            subprocess.run(  # nosec
                ["git", "config", "user.email", "evolver@aura.hive"],
                check=True,
                capture_output=True,
                cwd=root,
            )
            logger.info("git_identity_configured")
        except subprocess.CalledProcessError as e:
            logger.error(
                "git_config_failed",
                error=e.stderr.decode(errors="replace").strip(),
            )
            raise
