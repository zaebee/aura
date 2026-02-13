import time
from typing import Any

import structlog
from aura_core import (
    HiveContext,
    IntentAction,
    SkillRegistry,
    SystemVitals,
    Transformer,
    resolve_brain_path,
)
from aura_core.gen.aura.assets import v1 as asset_pb2
from aura_core.gen.aura.core.v1 import (
    ActionType,
    AssetIntent,
    ContextType,
    NegotiationIntent,
)

logger = structlog.get_logger(__name__)


def map_action(action_str: str | None) -> ActionType:
    """
    Standardized mapper for negotiation actions.
    Converts LLM strings to strict ActionType enum.
    """
    if not action_str:
        return ActionType.ACTION_TYPE_UNSPECIFIED

    mapping: dict[str, ActionType] = {
        "accept": ActionType.ACTION_TYPE_ACCEPT,
        "counter": ActionType.ACTION_TYPE_COUNTER,
        "counteroffer": ActionType.ACTION_TYPE_COUNTER,
        "reject": ActionType.ACTION_TYPE_REJECT,
        "ui_required": ActionType.ACTION_TYPE_UI_REQUIRED,
        "error": ActionType.ACTION_TYPE_ERROR,
    }
    return mapping.get(action_str.lower(), ActionType.ACTION_TYPE_UNSPECIFIED)


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
                identifier=request_id or "",
                action=ActionType.ACTION_TYPE_REJECT,
                reasoning="Item not found",
                negotiation=NegotiationIntent(
                    price=0.0,
                    message="Item not found",
                    thought="<think>Item not found. Rejecting.</think>",
                ),
                metadata={"reason_code": "ITEM_NOT_FOUND"},
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                identifier=request_id or "",
                action=ActionType.ACTION_TYPE_UI_REQUIRED,
                reasoning=f"Bid of ${bid} exceeds security threshold",
                negotiation=NegotiationIntent(
                    price=bid,
                    message=f"Bid of ${bid} exceeds security threshold",
                    thought="<think>Bid exceeds security threshold. UI confirmation required.</think>",
                ),
                metadata={"template_id": "high_value_confirm"},
            )

        floor_price = item_data.get("floor_price", 0.0)
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return IntentAction(
                identifier=request_id or "",
                action=ActionType.ACTION_TYPE_COUNTER,
                reasoning=f"Bid {bid} below floor {floor_price}. Countering.",
                negotiation=NegotiationIntent(
                    price=floor_price,
                    message=f"We cannot accept less than ${floor_price}.",
                    thought=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
                ),
                metadata={"reason_code": "BELOW_FLOOR"},
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            identifier=request_id or "",
            action=ActionType.ACTION_TYPE_ACCEPT,
            reasoning="Bid at or above floor price. Accepting.",
            negotiation=NegotiationIntent(
                price=bid,
                message="Offer accepted.",
                thought="<think>Bid at or above floor price. Accepting.</think>",
            ),
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
        )


class AuraTransformer(Transformer[HiveContext, IntentAction]):
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

    def _get_cpu_load(self, vitals: SystemVitals) -> float:
        if vitals:
            return float(vitals.cpu_usage_percent)
        return 0.0

    def _build_economic_context(self, context: HiveContext) -> dict:
        cpu_load = self._get_cpu_load(context.vitals)
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

        base_price = 0.0
        floor_price = 0.0
        meta = {}
        vision_result = None

        if context.hive and context.hive.asset_payload:
            asset = asset_pb2.Asset().parse(context.hive.asset_payload.value)
            if asset.rental_terms and asset.rental_terms.price_tiers:
                base_price = asset.rental_terms.price_tiers[0].price_per_day

            # Read meta from specifications
            if asset.vehicle and asset.vehicle.specifications:
                meta = dict(asset.vehicle.specifications)

            # Floor price was stored in metadata by persistence skill
            floor_price = float(context.metadata.get("floor_price", base_price * 0.8))

            if context.metadata.get("source") == "vision":
                vision_result = {
                    "make": asset.vehicle.brand,
                    "model": asset.vehicle.model,
                    "year": asset.vehicle.year,
                    "confidence_score": float(context.metadata.get("confidence_score", 0.0))
                }

        return {
            "base_price": base_price,
            "floor_price": floor_price,
            "reputation": context.hive.offer.reputation if context.hive else 1.0,
            "system_constraints": constraints,
            "meta": meta,
            "vision_result": vision_result,
            "vision_error": context.metadata.get("vision_error"),
            "vision_confidence_threshold": vision_confidence_threshold,
        }

    async def think(self, context: HiveContext, **kwargs: Any) -> IntentAction:
        """Reason about the negotiation by calling the Reasoning Protein."""

        # 1. Handle Polymorphic Search
        if context.context_type == ContextType.CONTEXT_TYPE_ASSET and context.asset:
             return IntentAction(
                 identifier=context.identifier,
                 action=ActionType.ACTION_TYPE_EVALUATE,
                 asset=AssetIntent(
                     asset_identifier="search",
                     asset_domain="VEHICLE",
                     action_type=ActionType.ACTION_TYPE_EVALUATE,
                     action_parameters={"query": context.asset.search_query}
                 )
             )

        # 2. Rule-based fallback if requested
        if self.settings and self.settings.llm.model.lower() == "rule":
            strategy = RuleBasedStrategy(
                trigger_price=self.settings.safety.ui_trigger_price
            )
            # Unpack asset data for rule-based
            asset_data = {}
            if context.hive and context.hive.asset_payload:
                asset = asset_pb2.Asset().parse(context.hive.asset_payload.value)
                asset_data = {
                    "base_price": asset.rental_terms.price_tiers[0].price_per_day if asset.rental_terms and asset.rental_terms.price_tiers else 0.0,
                    "floor_price": float(context.metadata.get("floor_price", 0.0)),
                }

            return strategy.evaluate(
                asset_data,
                context.hive.offer.bid_amount if context.hive else 0.0,
                context.hive.offer.reputation if context.hive else 1.0,
                context.hive.request_id if context.hive else context.identifier,
            )

        # 3. Dynamic Reasoning
        try:
            # Call Reasoning Protein
            obs = await self.registry.execute(
                "reasoning",
                "negotiate",
                {
                    "bid": context.hive.offer.bid_amount if context.hive else 0.0,
                    "context": self._build_economic_context(context),
                    "history": [],
                },
            )

            if not obs.success:
                logger.error("reasoning_protein_failed", error=obs.error)
                return IntentAction(
                    identifier=context.hive.request_id if context.hive else context.identifier,
                    action=ActionType.ACTION_TYPE_ERROR,
                    reasoning=obs.error or "unknown_error",
                )

            # Unpack NegotiationIntent from payload
            intent_proto = NegotiationIntent().parse(obs.payload.value)

            # Implement <think> tag logic for transparency
            raw_thought = intent_proto.thought
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            action_metadata = {
                **obs.metadata,
                "brain_path": self.brain_path,
            }

            # If it's a vision-based discovery or its confirmation, propagate result
            is_vision = context.metadata.get("source") == "vision"
            is_vision_confirm = (
                context.metadata.get("source") == "telegram"
                and "list_now" in context.metadata.get("callback_data", "")
            )
            if (is_vision or is_vision_confirm) and context.hive and context.hive.asset_payload:
                action_metadata["asset_discovered"] = "true"

            return IntentAction(
                identifier=context.hive.request_id if context.hive else context.identifier,
                action=map_action(obs.event_type), # Action string was passed in event_type
                reasoning=wrapped_thought,
                negotiation=NegotiationIntent(
                    price=intent_proto.price,
                    message=intent_proto.message,
                    thought=wrapped_thought,
                ),
                metadata=action_metadata,
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return IntentAction(
                identifier=context.hive.request_id if context.hive else context.identifier,
                action=ActionType.ACTION_TYPE_ERROR,
                reasoning=str(e),
            )
