import time
from typing import Any

import structlog
from aura_core import (
    FailureIntent,
    HiveContext,
    IntentAction,
    SkillRegistry,
    SystemVitals,
    Transformer,
)

logger = structlog.get_logger(__name__)


class RuleBasedStrategy:
    """
    Rule-based pricing strategy that doesn't require an LLM.
    Integrated into Transformer as a fallback/deterministic mode.
    """

    def __init__(
        self,
        trigger_price: float = 1000.0,
    ):
        self.trigger_price = trigger_price

    def evaluate(
        self,
        item_data: dict[str, Any],
        bid: float,
        reputation: float,
        request_id: str | None = None,
    ) -> IntentAction:
        if not item_data:
            return IntentAction(
                action="reject",
                price=0.0,
                message="Item not found",
                metadata={"reason_code": "ITEM_NOT_FOUND"},
                thought="<think>Item not found. Rejecting.</think>",
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                action="ui_required",
                price=bid,
                message=f"Bid of ${bid} exceeds security threshold",
                metadata={"template_id": "high_value_confirm"},
                thought="<think>Bid exceeds security threshold. UI confirmation required.</think>",
            )

        floor_price = item_data.get("floor_price", 0.0)
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return IntentAction(
                action="counter",
                price=floor_price,
                message=f"We cannot accept less than ${floor_price}.",
                metadata={"reason_code": "BELOW_FLOOR"},
                thought=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            action="accept",
            price=bid,
            message="Offer accepted.",
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
            thought="<think>Bid at or above floor price. Accepting.</think>",
        )


class AuraTransformer(Transformer[HiveContext, IntentAction]):
    """T - Transformer: Pure reasoning engine calling Reasoning Protein."""

    def __init__(self, registry: SkillRegistry, settings: Any = None):
        self.settings = settings
        self.registry = registry

    def _get_cpu_load(self, system_health: SystemVitals | dict[str, Any]) -> float:
        if isinstance(system_health, SystemVitals):
            return float(system_health.cpu_usage_percent)
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
        """Reason about the negotiation by calling the Reasoning Protein."""

        # Rule-based fallback if requested
        if self.settings and self.settings.llm.model.lower() == "rule":
            strategy = RuleBasedStrategy(
                trigger_price=self.settings.safety.ui_trigger_price
            )
            return strategy.evaluate(
                context.item_data,
                context.offer.bid_amount,
                context.offer.reputation,
                context.request_id,
            )

        try:
            # Call Reasoning Protein
            obs = await self.registry.execute(
                "reasoning",
                "negotiate",
                {
                    "bid": context.offer.bid_amount,
                    "context": self._build_economic_context(context),
                    "history": [],
                },
            )

            if not obs.success:
                logger.error("reasoning_protein_failed", error=obs.error)
                return FailureIntent(error=obs.error or "unknown_error")

            result = obs.data

            # Implement <think> tag logic for transparency
            raw_thought = result.get("thought", "")
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            return IntentAction(
                action=result["action"],
                price=result["price"],
                message=result["message"],
                thought=wrapped_thought,
                metadata=result.get("metadata", {}),
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return FailureIntent(error=str(e))
