import asyncio
import json
import time
from pathlib import Path

import dspy
import nats
import structlog

from src.config import get_settings
from src.llm.engine import AuraNegotiator

from .types import FailureIntent, HiveContext, IntentAction

logger = structlog.get_logger(__name__)

# Brain search paths in priority order (Docker path first, then local dev paths)
BRAIN_SEARCH_PATHS = [
    "/app/data/aura_brain.json",  # Docker container path (primary)
    "/app/src/aura_brain.json",  # Legacy Docker path
    "data/aura_brain.json",  # Local dev path (relative to core-service)
]


class AuraTransformer:
    """T - Transformer: Pure reasoning engine using DSPy."""

    def __init__(self, compiled_program_path: str | None = None):
        self.settings = get_settings()
        self.compiled_program_path = (
            compiled_program_path or self.settings.llm.compiled_program_path
        )
        self.brain_loaded = False
        self.brain_path: str | None = None

        # Default configuration
        dspy.configure(lm=dspy.LM(self.settings.llm.model))
        self.negotiator = self._load_negotiator()

    def _find_brain_path(self) -> Path | None:
        """Search for aura_brain.json in priority order."""
        # First check explicit path from settings
        explicit_path = Path(self.compiled_program_path)
        if explicit_path.is_absolute() and explicit_path.exists():
            return explicit_path

        # Check standard search paths
        for search_path in BRAIN_SEARCH_PATHS:
            path = Path(search_path)
            if path.exists():
                logger.info("brain_found", path=str(path))
                return path

        # Fallback: check relative to this file (for local dev)
        relative_path = Path(__file__).parent.parent / self.compiled_program_path
        if relative_path.exists():
            return relative_path

        return None

    async def _emit_brain_dead_event(self, searched_paths: list[str]) -> None:
        """Emit NATS event when brain cannot be found."""
        try:
            nc = await nats.connect(self.settings.server.nats_url)
            event = {
                "event": "aura.core.brain_dead",
                "timestamp": time.time(),
                "searched_paths": searched_paths,
                "message": "Transformer brain (aura_brain.json) not found. Running untrained.",
            }
            await nc.publish("aura.core.brain_dead", json.dumps(event).encode())
            await nc.flush()
            await nc.close()
            logger.warning("brain_dead_event_emitted", paths=searched_paths)
        except Exception as e:
            logger.error("failed_to_emit_brain_dead_event", error=str(e))

    def _load_negotiator(self) -> AuraNegotiator:
        """Load the compiled DSPy program with failsafe path resolution."""
        try:
            brain_path = self._find_brain_path()

            if brain_path and brain_path.exists():
                logger.info("loading_compiled_dspy_program", path=str(brain_path))
                self.brain_loaded = True
                self.brain_path = str(brain_path)
                return dspy.load(str(brain_path))  # type: ignore
            else:
                # Brain not found - emit event asynchronously
                searched = BRAIN_SEARCH_PATHS + [self.compiled_program_path]
                logger.warning(
                    "brain_not_found_using_untrained",
                    searched_paths=searched,
                )
                # Schedule NATS event emission (non-blocking)
                try:
                    # If a loop is running, create a task. This is non-blocking.
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._emit_brain_dead_event(searched))
                except RuntimeError:
                    # No running loop. We are in a sync context.
                    # Run the async function in a new event loop. This is blocking,
                    # but acceptable for a one-off event on startup.
                    asyncio.run(self._emit_brain_dead_event(searched))
                return AuraNegotiator()
        except Exception as e:
            logger.error("failed_to_load_dspy_program", error=str(e))
            return AuraNegotiator()

    def _build_economic_context(self, context: HiveContext) -> dict:
        """Construct pure economic context without infrastructure leakage."""
        cpu_load = context.system_health.get("cpu_usage_percent", 0.0)
        constraints = []
        if cpu_load > 80.0:
            constraints.append("SYSTEM_LOAD_HIGH: Be extremely concise.")

        return {
            "base_price": context.item_data.get("base_price", 0.0),
            "floor_price": context.item_data.get("floor_price", 0.0),
            "reputation": context.offer.reputation,
            "system_constraints": constraints,
            "meta": context.item_data.get("meta", {}),
        }

    async def think(self, context: HiveContext) -> IntentAction:
        """
        Reason about the negotiation using self-reflective tuning.
        Returns a strictly typed IntentAction.
        """
        cpu_load = context.system_health.get("cpu_usage_percent", 0.0)

        # Self-reflective tuning: adjust model and temperature based on system health
        model = self.settings.llm.model
        temperature = self.settings.llm.temperature

        if cpu_load > 80.0:
            # Switch to a faster model and lower temperature for speed/determinism
            model = "mistral-small-latest"
            temperature = 0.1
            logger.warning(
                "reflective_tuning_applied",
                reason="high_cpu",
                cpu_load=cpu_load,
                model=model,
            )

        try:
            # Use dspy.context for request-scoped model configuration
            with dspy.context(lm=dspy.LM(model, temperature=temperature)):
                result = await asyncio.to_thread(
                    self.negotiator,
                    input_bid=context.offer.bid_amount,
                    context=self._build_economic_context(context),
                    history=[],  # History tracking planned for future iterations
                )

            action_data = result["action"]

            logger.info(
                "transformer_thought_complete",
                action=action_data.get("action"),
                price=action_data.get("price"),
            )

            return IntentAction(
                action=action_data["action"],
                price=action_data["price"],
                message=action_data["message"],
                thought=result.get("thought", ""),
                metadata={"dspy_result": result, "model_used": model},
            )

        except (ValueError, KeyError, TypeError, RuntimeError) as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            # Return FailureIntent which the Membrane will handle
            return FailureIntent(
                error=str(e),
                metadata={"context": str(context)},
            )
