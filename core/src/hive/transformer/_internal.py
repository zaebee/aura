import time
from typing import Any

from aura_core import IntentAction


class RuleBasedStrategy:
    """
    Rule-based pricing strategy that doesn't require an LLM.
    Integrated into Transformer as a fallback/deterministic mode.
    """

    def __init__(
        self,
        # TODO: The trigger_price is hardcoded with a default value of 1000.0.
        # This value acts as a security threshold for requiring UI confirmation
        # on high-value bids. For better maintainability and flexibility,
        # consider making this value configurable through a settings class,
        # such as SafetySettings.
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
