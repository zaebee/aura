import asyncio
from pathlib import Path

import dspy
import structlog

from src.config import get_settings
from src.llm.engine import AuraNegotiator

from .types import FailureIntent, HiveContext, IntentAction

logger = structlog.get_logger(__name__)


class AuraTransformer:
    """T - Transformer: Pure reasoning engine using DSPy."""

    def __init__(self, compiled_program_path: str | None = None):
        self.settings = get_settings()
        self.compiled_program_path = (
            compiled_program_path or self.settings.llm.compiled_program_path
        )

        # Default configuration
        dspy.configure(lm=dspy.LM(self.settings.llm.model))
        self.negotiator = self._load_negotiator()

    def _load_negotiator(self) -> AuraNegotiator:
        try:
            program_path = Path(self.compiled_program_path)
            if not program_path.is_absolute():
                program_path = Path(__file__).parent.parent / self.compiled_program_path

            if program_path.exists():
                logger.info("loading_compiled_dspy_program", path=str(program_path))
                return dspy.load(str(program_path))  # type: ignore
            else:
                logger.warning(
                    "compiled_program_not_found_using_untrained", path=str(program_path)
                )
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
