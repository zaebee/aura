from typing import Any
import time
from aura_core import IntentAction, HiveContext

class RuleBasedStrategy:
    """
    Rule-based pricing strategy that doesn't require an LLM.
    Kept for backward compatibility and as a deterministic fallback.
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
            )

        # Rule: High-value bids require UI confirmation
        if bid > self.trigger_price:
            return IntentAction(
                action="ui_required",
                price=bid,
                message=f"Bid of ${bid} exceeds security threshold",
                metadata={"template_id": "high_value_confirm"},
            )

        floor_price = item_data.get("floor_price", 0.0)
        # Rule: Bid below floor price - counter with floor price
        if bid < floor_price:
            return IntentAction(
                action="counter",
                price=floor_price,
                message=f"We cannot accept less than ${floor_price}.",
                thought="<think>RuleBased: Bid below floor.</think>",
                metadata={"reason_code": "BELOW_FLOOR"},
            )

        # Rule: Bid at or above floor price - accept
        return IntentAction(
            action="accept",
            price=bid,
            message="Offer accepted.",
            thought="<think>RuleBased: Bid above floor.</think>",
            metadata={"reservation_code": f"RULE-{int(time.time())}"},
        )

from .transformer import AuraTransformer

__all__ = ["AuraTransformer", "RuleBasedStrategy"]
