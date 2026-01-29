from typing import Any

import structlog
from hive.dna import Decision, HiveContext

from config import get_settings

logger = structlog.get_logger(__name__)

DEFAULT_MIN_MARGIN = 0.1


class HiveMembrane:
    """The Immune System: Deterministic Guardrails for Inbound/Outbound signals."""

    def __init__(self):
        self.settings = get_settings()

    async def inspect_inbound(self, signal: Any) -> Any:
        """
        Sanitize inbound signals to protect against prompt injection.

        Args:
            signal: The inbound gRPC request.
        """
        if hasattr(signal, "bid_amount") and signal.bid_amount <= 0:
            logger.warning(
                "membrane_inbound_invalid_bid",
                bid_amount=signal.bid_amount,
                error="Bid amount must be positive",
            )
            raise ValueError("Bid amount must be positive")

        # Common prompt injection patterns
        injection_patterns = [
            "ignore all previous instructions",
            "ignore previous instructions",
            "system override",
            "act as a",
            "you are now",
            "disregard",
        ]

        # Scan string fields for injection attempts
        # We look at item_id and agent DID/metadata if available
        fields_to_scan = []
        if hasattr(signal, "item_id"):
            fields_to_scan.append(("item_id", signal.item_id))

        if hasattr(signal, "agent") and hasattr(signal.agent, "did"):
            fields_to_scan.append(("agent.did", signal.agent.did))

        for field_name, value in fields_to_scan:
            if isinstance(value, str):
                lowered_val = value.lower()
                for pattern in injection_patterns:
                    if pattern in lowered_val:
                        logger.warning(
                            "membrane_inbound_injection_detected",
                            field=field_name,
                            pattern=pattern,
                        )
                        # Sanitize by clearing or marking the signal as suspicious
                        # In a real scenario, we might raise an error here.
                        # For now, we'll just redact the suspicious part.
                        if field_name == "item_id":
                            signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"
                        elif field_name == "agent.did":
                            signal.agent.did = "REDACTED"

        return signal

    async def inspect_outbound(
        self, decision: Decision, context: HiveContext
    ) -> Decision:
        """
        Enforce hard economic rules on outbound decisions.

        Rule 1: NEVER accept a price below floor_price.
        Rule 2: Ensure margin >= settings.logic.min_margin.
        """
        floor_price = context.item_data.get("floor_price", 0.0)
        min_margin = self.settings.logic.min_margin

        # If LLM didn't return a price (e.g. reject), just pass through
        if decision.action not in ["accept", "counter"]:
            return decision

        # 1. Floor Price Check
        if decision.price < floor_price:
            logger.warning(
                "membrane_rule_violation",
                rule="floor_price",
                proposed=decision.price,
                floor=floor_price,
            )
            return self._override_with_safe_offer(
                decision, floor_price, "FLOOR_PRICE_VIOLATION"
            )

        # 2. Min Margin Check
        # Margin = (Price - Floor) / Price
        # Required: (P - F) / P >= m  => P - F >= mP => P(1-m) >= F => P >= F / (1-m)
        if min_margin >= 1.0:
            logger.error("invalid_min_margin_config", margin=min_margin)
            min_margin = DEFAULT_MIN_MARGIN  # Fallback to constant

        required_min_price = floor_price / (1 - min_margin)

        if decision.price < required_min_price:
            logger.warning(
                "membrane_rule_violation",
                rule="min_margin",
                proposed=decision.price,
                required=required_min_price,
            )
            return self._override_with_safe_offer(
                decision, required_min_price, "MIN_MARGIN_VIOLATION"
            )

        return decision

    def _override_with_safe_offer(
        self, original: Decision, safe_price: float, reason: str
    ) -> Decision:
        """Override an unsafe decision with a safe counter-offer."""
        return Decision(
            action="counter",
            price=round(safe_price, 2),
            message=f"I've reached my final limit for this item. My best offer is ${safe_price:.2f}.",
            reasoning=f"Membrane Override: {reason}. LLM suggested {original.price}.",
            metadata={
                "original_decision": original.action,
                "original_price": original.price,
                "override_reason": reason,
            },
        )
