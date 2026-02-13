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
from aura_core.gen.aura.core.v1 import (
    ActionType,
    Context,
    ContextType,
    Intent,
    NegotiationIntent,
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
        context: Context,
        request_id: str | None = None,
    ) -> Intent:
        item_data = context.metadata
        bid = 0.0
        if context.hive and context.hive.offer:
            bid = context.hive.offer.bid_amount

        if not item_data.get("item_name"):
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                reasoning="<think>Item not found. Rejecting.</think>",
                metadata={"reason_code": "ITEM_NOT_FOUND"},
                negotiation=NegotiationIntent(
                    price=0.0,
                    message="Item not found",
                ),
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_EVALUATE), # UI REQUIRED Surrogate
                reasoning="<think>Bid exceeds security threshold. UI confirmation required.</think>",
                metadata={"template_id": "high_value_confirm"},
                negotiation=NegotiationIntent(
                    price=bid,
                    message=f"Bid of ${bid} exceeds security threshold",
                ),
            )

        floor_price = float(item_data.get("floor_price", "0.0"))
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
                reasoning=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
                metadata={"reason_code": "BELOW_FLOOR"},
                negotiation=NegotiationIntent(
                    price=floor_price,
                    message=f"We cannot accept less than ${floor_price}.",
                ),
            )

        # Rule: Bid at or above floor price - accept
        return Intent(
            action=cast(ActionType, ActionType.ACTION_TYPE_ACCEPT),
            reasoning="<think>Bid at or above floor price. Accepting.</think>",
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
            negotiation=NegotiationIntent(
                price=bid,
                message="Offer accepted.",
            ),
        )


class AuraTransformer(Transformer[Context, Intent]):
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
        self.brain_path = resolve_brain_path(compiled_path or "")

    def _get_cpu_load(self, context: Context) -> float:
        vitals_json = context.metadata.get("vitals_json")
        if vitals_json:
            try:
                vitals_dict = json.loads(vitals_json)
                return float(vitals_dict.get("cpu_usage_percent", 0.0))
            except Exception:
                pass
        return 0.0

    def _build_economic_context(self, context: Context) -> dict:
        cpu_load = self._get_cpu_load(context)
        constraints = []
        if cpu_load > 80.0:
            constraints.append("SYSTEM_LOAD_HIGH: Be extremely concise.")

        # Rely on single source of truth for configuration
        vision_confidence_threshold = 0.7
        if (
            self.settings
            and hasattr(self.settings, "perception")
            and hasattr(self.settings.perception, "confidence_threshold")
        ):
            vision_confidence_threshold = self.settings.perception.confidence_threshold

        bid = 0.0
        reputation = 1.0
        if context.hive and context.hive.offer:
            bid = context.hive.offer.bid_amount
            reputation = context.hive.offer.reputation

        return {
            "base_price": float(context.metadata.get("base_price", "0.0")),
            "floor_price": float(context.metadata.get("floor_price", "0.0")),
            "reputation": reputation,
            "system_constraints": constraints,
            "meta": context.metadata,
            "vision_result": context.metadata
            if context.metadata.get("source") == "vision"
            else None,
            "vision_error": context.metadata.get("vision_error"),
            "vision_confidence_threshold": vision_confidence_threshold,
        }

    async def think(self, context: Context, **kwargs: Any) -> Intent:
        """Reason about the negotiation by calling the Reasoning Protein."""

        # Rule-based fallback if requested
        if (
            self.settings
            and hasattr(self.settings, "llm")
            and hasattr(self.settings.llm, "model")
            and self.settings.llm.model.lower() == "rule"
        ):
            strategy = RuleBasedStrategy(
                trigger_price=getattr(self.settings.safety, "ui_trigger_price", 1000.0)
            )
            return strategy.evaluate(context)

        try:
            bid = 0.0
            if context.hive and context.hive.offer:
                bid = context.hive.offer.bid_amount

            # Call Reasoning Protein
            obs = await self.registry.execute(
                "reasoning",
                "negotiate",
                {
                    "bid": bid,
                    "context": self._build_economic_context(context),
                    "history": [],
                },
            )

            if not obs.success:
                logger.error("reasoning_protein_failed", error=obs.error)
                return Intent(
                    action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                    reasoning=f"<think>Reasoning failed: {obs.error}</think>",
                    negotiation=NegotiationIntent(message="Internal processing error.")
                )

            # reasoning protein returns data in metadata
            result = getattr(obs, "metadata", {})

            # Implement <think> tag logic for transparency
            raw_thought = result.get("thought", "")
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            action_metadata = {
                **{k: str(v) for k, v in result.items() if k not in ["action", "price", "message", "thought"]},
                "brain_path": self.brain_path,
            }

            return Intent(
                action=cast(ActionType, map_action(str(result.get("action", "")))),
                reasoning=wrapped_thought,
                metadata=action_metadata,
                negotiation=NegotiationIntent(
                    price=float(result.get("price", 0.0)),
                    message=str(result.get("message", "")),
                    thought=str(result.get("thought", "")),
                )
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                reasoning=f"<think>Transformer exception: {str(e)}</think>",
                negotiation=NegotiationIntent(message="Internal transformer error.")
            )
