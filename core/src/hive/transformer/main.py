import json
import time
from typing import Any, cast

import structlog
from aura_core import (
    SkillRegistry,
    Transformer,
    map_action,
    resolve_brain_path,
)
from aura_core.gen.aura.dna.v1 import (
    ActionType,
    Context,
    ItemData,
    NegotiationIntent,
    SystemVitals,
)
from aura_core.gen.aura.dna.v1 import (
    Intent as IntentAction,
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
        item_data: ItemData,
        bid: float,
        reputation: float,
        request_id: str | None = None,
    ) -> IntentAction:
        # Resilience for tests/legacy passing dicts
        floor_price = getattr(
            item_data,
            "floor_price",
            item_data.get("floor_price", 0.0) if isinstance(item_data, dict) else 0.0,
        )
        identifier = getattr(
            item_data,
            "identifier",
            item_data.get("identifier", "unknown")
            if isinstance(item_data, dict)
            else "",
        )

        if not item_data or (not identifier and not floor_price):
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                reasoning="<think>Item not found. Rejecting.</think>",
                negotiation=NegotiationIntent(
                    price=0.0,
                    message="Item not found",
                ),
                metadata={"reason_code": "ITEM_NOT_FOUND"},
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_UI_REQUIRED),
                reasoning="<think>Bid exceeds security threshold. UI confirmation required.</think>",
                negotiation=NegotiationIntent(
                    price=bid,
                    message=f"Bid of ${bid} exceeds security threshold",
                ),
                metadata={"template_id": "high_value_confirm"},
            )

        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
                reasoning=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
                negotiation=NegotiationIntent(
                    price=floor_price,
                    message=f"We cannot accept less than ${floor_price}.",
                ),
                metadata={"reason_code": "BELOW_FLOOR"},
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            action=cast(ActionType, ActionType.ACTION_TYPE_ACCEPT),
            reasoning="<think>Bid at or above floor price. Accepting.</think>",
            negotiation=NegotiationIntent(
                price=bid,
                message="Offer accepted.",
            ),
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
        )


class AuraTransformer(Transformer[Context, IntentAction]):
    """T - Transformer: Pure reasoning engine calling Reasoning Protein."""

    def __init__(self, registry: SkillRegistry, settings: Any = None):
        self.settings = settings
        self.registry = registry
        compiled_path = None
        if (
            settings
            and hasattr(settings, "llm")
            and hasattr(settings.llm, "compiled_program_path")
        ):
            compiled_path = settings.llm.compiled_program_path
        self.brain_path = resolve_brain_path(compiled_path)

    def _get_cpu_load(self, system_health: SystemVitals) -> float:
        return float(system_health.cpu_usage_percent)

    def _build_economic_context(self, context: Context) -> dict:
        cpu_load = self._get_cpu_load(context.system_health)
        constraints = []
        if cpu_load > 80.0:
            constraints.append("SYSTEM_LOAD_HIGH: Be extremely concise.")

        hive = context.hive
        return {
            "base_price": hive.item.base_price,
            "floor_price": hive.item.floor_price,
            "reputation": hive.offer.reputation,
            "system_constraints": constraints,
            "meta": hive.item.meta,
        }

    async def think(self, context: Context, **kwargs: Any) -> IntentAction:
        """Reason about the negotiation by calling the Reasoning Protein."""

        hive = context.hive
        # Rule-based fallback if requested
        if self.settings and self.settings.llm.model.lower() == "rule":
            strategy = RuleBasedStrategy(
                trigger_price=self.settings.safety.ui_trigger_price
            )
            return strategy.evaluate(
                hive.item,
                hive.offer.price,
                hive.offer.reputation,
                hive.request_id,
            )

        try:
            # Call Reasoning Protein
            obs = await self.registry.execute(
                "reasoning",
                "negotiate",
                {
                    "bid": hive.offer.price,
                    "context": self._build_economic_context(context),
                    "history": [],
                },
            )

            if not obs.success:
                logger.error("reasoning_protein_failed", error=obs.error)
                return IntentAction(
                    action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                    negotiation=NegotiationIntent(
                        message=f"Internal processing error: {obs.error or 'unknown'}"
                    ),
                )

            result = json.loads(obs.metadata.get("negotiation_result", "{}"))

            # Implement <think> tag logic for transparency
            raw_thought = result.get("thought", "")
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            return IntentAction(
                action=map_action(result["action"]),
                reasoning=wrapped_thought,
                negotiation=NegotiationIntent(
                    price=result["price"],
                    message=result["message"],
                    thought=wrapped_thought,
                ),
                metadata={
                    **result.get("metadata", {}),
                    "brain_path": self.brain_path,
                },
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return IntentAction(
                action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                negotiation=NegotiationIntent(message=f"Fatal error: {str(e)}"),
            )
