import time
from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    SkillRegistry,
    Transformer,
    make_struct,
    map_action,
    resolve_brain_path,
)
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    NegotiationIntent,
    TradeIntent,
    ValidationScore,
)

logger = structlog.get_logger(__name__)


def _get_hive(context: Context) -> Any:
    """Safely extract HiveContextData from Context.data oneof — returns None for non-hive contexts."""
    name, value = betterproto.which_one_of(context, "data")
    return value if name == "hive" else None


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
        item_data = context.metadata.to_dict()
        bid = 0.0
        hive = _get_hive(context)
        if hive and hive.offer:
            bid = hive.offer.bid_amount

        if not item_data.get("item_name"):
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_REJECT),
                reasoning="<think>Item not found. Rejecting.</think>",
                metadata=make_struct({"reason_code": "ITEM_NOT_FOUND"}),
                negotiation=NegotiationIntent(
                    price=0.0,
                    message="Item not found",
                ),
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return Intent(
                action=cast(
                    ActionType, ActionType.ACTION_TYPE_EVALUATE
                ),  # UI REQUIRED Surrogate
                reasoning="<think>Bid exceeds security threshold. UI confirmation required.</think>",
                metadata=make_struct({"template_id": "high_value_confirm"}),
                negotiation=NegotiationIntent(
                    price=bid,
                    message=f"Bid of ${bid} exceeds security threshold",
                ),
            )

        floor_price = float(str(item_data.get("floor_price", 0.0)))
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_COUNTER),
                reasoning=f"<think>Bid {bid} below floor {floor_price}. Countering.</think>",
                metadata=make_struct({"reason_code": "BELOW_FLOOR"}),
                negotiation=NegotiationIntent(
                    price=floor_price,
                    message=f"We cannot accept less than ${floor_price}.",
                ),
            )

        # Rule: Bid at or above floor price - accept
        return Intent(
            action=cast(ActionType, ActionType.ACTION_TYPE_ACCEPT),
            reasoning="<think>Bid at or above floor price. Accepting.</think>",
            metadata=make_struct({"reservation_code": f"RULE-{int(time.time())}"}),
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

    def _get_cpu_load(self, metadata: dict[str, Any]) -> float:
        vitals = metadata.get("vitals")
        if isinstance(vitals, dict):
            return float(vitals.get("cpu_usage_percent", 0.0))
        return 0.0

    def _build_economic_context(self, context: Context) -> dict[str, Any]:
        metadata = context.metadata.to_dict()
        cpu_load = self._get_cpu_load(metadata)
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

        reputation = 1.0
        hive = _get_hive(context)
        if hive and hive.offer:
            reputation = hive.offer.reputation

        return {
            "base_price": float(str(metadata.get("base_price", 0.0))),
            "floor_price": float(str(metadata.get("floor_price", 0.0))),
            "reputation": reputation,
            "system_constraints": constraints,
            "meta": metadata,
            "vision_result": metadata if metadata.get("source") == "vision" else None,
            "vision_error": metadata.get("vision_error"),
            "vision_confidence_threshold": vision_confidence_threshold,
        }

    def _is_trade_context(self, metadata: dict[str, Any]) -> bool:
        """Return True when the context carries a trade signal."""
        if metadata.get("trade_mode") == "true":
            return True
        if metadata.get("asset_domain"):
            return True
        return False

    def _build_trade_context(
        self, metadata: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Extract market_context, system_vitals, current_treasury from metadata."""
        market_context: dict[str, Any] = {
            "prices": metadata.get("prices", {}),
            "vision_result": metadata.get("vision_result"),
            "asset_domain": metadata.get("asset_domain", ""),
            "asset_identifier": metadata.get("asset_identifier", ""),
        }
        system_vitals: dict[str, Any] = dict(metadata.get("vitals") or {})
        current_treasury: dict[str, Any] = dict(metadata.get("treasury") or {})
        return market_context, system_vitals, current_treasury

    async def _think_trade(self, context: Context, metadata: dict[str, Any]) -> Intent:
        """Trade path: invoke GenerateTradeIntent via the reasoning protein."""
        market_context, system_vitals, current_treasury = self._build_trade_context(
            metadata
        )

        obs = await self.registry.execute(
            "reasoning",
            "trade",
            {
                "market_context": market_context,
                "system_vitals": system_vitals,
                "current_treasury": current_treasury,
            },
        )

        if not obs.success:
            logger.error("trade_reasoning_failed", error=obs.error)
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                reasoning=f"<think>Trade reasoning failed: {obs.error}</think>",
                trade=TradeIntent(reasoning=f"ERROR: {obs.error}"),
            )

        raw = obs.metadata.to_dict() if obs.metadata else {}
        trade_data: dict[str, Any] = raw.get("trade") or {}
        risk_score = float(str(raw.get("risk_score", "0.0")))
        risk_category = str(raw.get("risk_category", "LOW"))
        raw_think = str(raw.get("think", ""))
        wrapped_think = f"<think>\n{raw_think}\n</think>" if raw_think else ""

        validation_score = ValidationScore(
            risk_score=risk_score,
            risk_category=risk_category,
        )

        trade_intent = TradeIntent(
            trade_id=str(trade_data.get("trade_id", "")),
            asset_identifier=str(trade_data.get("asset_identifier", "")),
            asset_domain=str(trade_data.get("asset_domain", "")),
            proposed_price=float(trade_data.get("proposed_price", 0.0)),
            currency_code=str(trade_data.get("currency_code", "USDC")),
            reasoning=str(trade_data.get("reasoning", "")),
            validation_score=validation_score,
        )

        is_high_risk = risk_score > 0.10 or "REJECTED_HIGH_RISK" in trade_intent.reasoning
        action = (
            ActionType.ACTION_TYPE_REJECT if is_high_risk else ActionType.ACTION_TYPE_ACCEPT
        )

        if is_high_risk:
            logger.warning(
                "trade_rejected_high_risk",
                risk_score=risk_score,
                risk_category=risk_category,
            )

        return Intent(
            action=cast(ActionType, action),
            reasoning=wrapped_think,
            metadata=make_struct({"brain_path": self.brain_path}),
            trade=trade_intent,
        )

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
            metadata = context.metadata.to_dict()

            # Trade path: ERC-8004 structured trade intent generation
            if self._is_trade_context(metadata):
                return await self._think_trade(context, metadata)

            bid = 0.0
            hive = _get_hive(context)
            if hive and hive.offer:
                bid = hive.offer.bid_amount

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
                    negotiation=NegotiationIntent(message="Internal processing error."),
                )

            # reasoning protein returns data in metadata
            result_struct = getattr(obs, "metadata", None)
            raw_result = (
                result_struct.to_dict()
                if result_struct and hasattr(result_struct, "to_dict")
                else {}
            )

            # DSPy AuraNegotiator returns { "thought": ..., "action": { "action": ..., "price": ..., "message": ... } }
            # Extract nested action data correctly (Fixes Action 0 paralysis)
            action_data = raw_result.get("action")
            if not isinstance(action_data, dict):
                # Fallback if it's already flat or in another format
                action_data = raw_result

            # Implement <think> tag logic for transparency
            raw_thought = raw_result.get("thought", action_data.get("thought", ""))
            wrapped_thought = f"<think>\n{raw_thought}\n</think>" if raw_thought else ""

            action_metadata = {
                **{
                    k: str(v)
                    for k, v in raw_result.items()
                    if k not in ["action", "price", "message", "thought"]
                },
                "brain_path": self.brain_path,
            }

            return Intent(
                action=cast(ActionType, map_action(str(action_data.get("action", "")))),
                reasoning=wrapped_thought,
                metadata=make_struct(action_metadata),
                negotiation=NegotiationIntent(
                    price=float(action_data.get("price", 0.0)),
                    message=str(action_data.get("message", "")),
                    thought=str(raw_thought),
                ),
            )

        except Exception as e:
            logger.error("transformer_error", error=str(e), exc_info=True)
            return Intent(
                action=cast(ActionType, ActionType.ACTION_TYPE_ERROR),
                reasoning=f"<think>Transformer exception: {str(e)}</think>",
                negotiation=NegotiationIntent(message="Internal transformer error."),
            )
