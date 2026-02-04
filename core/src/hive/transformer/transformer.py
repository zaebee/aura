import asyncio
from typing import Any

import structlog
from aura_core import (
    FailureIntent,
    HiveContext,
    IntentAction,
    SystemVitals,
    Transformer,
    SkillRegistry
)

from config import get_settings

logger = structlog.get_logger(__name__)

class AuraTransformer(Transformer[HiveContext, IntentAction]):
    """T - Transformer: Pure reasoning engine orchestrator."""

    def __init__(self, registry: SkillRegistry | None = None):
        self.settings = get_settings()
        self.registry = registry or SkillRegistry()

    def _get_cpu_load(self, system_health: SystemVitals | dict[str, Any]) -> float:
        if isinstance(system_health, SystemVitals):
            return system_health.cpu_usage_percent
        return float(system_health.get("cpu_usage_percent", 0.0))

    def _build_economic_context(self, context: HiveContext) -> dict:
        cpu_load = self._get_cpu_load(context.system_health)
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

    async def think(self, context: HiveContext, **kwargs: Any) -> IntentAction:
        """
        Reason about the negotiation by calling the Reasoning Protein.
        Implements <think> tag logic for internal monologue.
        """
        # 1. Check for Rule mode
        if self.settings.llm.model == "rule":
             return self._rule_fallback(context)

        reasoning = self.registry.get("reasoning")
        if not reasoning:
            return self._rule_fallback(context)

        cpu_load = self._get_cpu_load(context.system_health)

        # Self-reflective tuning: adjust params via skill execution
        model = self.settings.llm.model
        temperature = self.settings.llm.temperature
        if cpu_load > 80.0:
            model = "mistral-small-latest"
            temperature = 0.1

        try:
            obs = await reasoning.execute("negotiate", {
                "input_bid": context.offer.bid_amount,
                "context": self._build_economic_context(context),
                "model": model,
                "temperature": temperature
            })

            if not obs.success:
                return FailureIntent(error=obs.error)

            result = obs.data
            action_data = result["action"]

            # IMPLEMENT <think> tag logic
            thought = result.get("thought", "")
            if thought and not (thought.strip().startswith("<think>") and thought.strip().endswith("</think>")):
                thought = f"<think>\n{thought}\n</think>"

            return IntentAction(
                action=action_data["action"],
                price=action_data["price"],
                message=action_data["message"],
                thought=thought,
                metadata={"model_used": model},
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return FailureIntent(error=str(e))

    def _rule_fallback(self, context: HiveContext) -> IntentAction:
        from hive.transformer import RuleBasedStrategy
        strategy = RuleBasedStrategy()
        return strategy.evaluate(
            context.item_data,
            context.offer.bid_amount,
            context.offer.reputation,
            context.request_id,
        )
