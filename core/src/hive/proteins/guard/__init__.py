from typing import Any

from aura_core import Observation, SkillProtocol
from config import get_settings


class GuardProtein(SkillProtocol[dict[str, Any], Observation]):
    """
    Guard Protein: Encapsulates safety validation and guardrails.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_name(self) -> str:
        return "guard"

    def get_capabilities(self) -> list[str]:
        return ["validate_margin", "validate_floor", "sanitize_input"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "sanitize_input":
            return self._sanitize_input(params.get("signal"))
        elif intent == "validate_decision":
            return self._validate_decision(params.get("decision"), params.get("context"))

        return Observation(success=False, error=f"Unknown intent: {intent}")

    def _sanitize_input(self, signal: Any) -> Observation:
        # Ported logic from HiveMembrane.inspect_inbound
        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
        ]

        # Note: This modifies the signal object in place if it's passed as such
        # In a pure Skill environment, we should probably return a sanitized copy or dict
        if hasattr(signal, "item_id"):
            val = str(signal.item_id).lower()
            for pattern in injection_patterns:
                if pattern in val:
                    signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"
                    break

        if hasattr(signal, "agent") and hasattr(signal.agent, "did"):
            val = str(signal.agent.did).lower()
            for pattern in injection_patterns:
                if pattern in val:
                    signal.agent.did = "REDACTED"
                    break

        return Observation(success=True, data=signal)

    def _validate_decision(self, decision_data: dict[str, Any], context_data: dict[str, Any]) -> Observation:
        # Ported logic from HiveMembrane.inspect_outbound (simplified for Protein)
        floor_price = context_data.get("floor_price", 0.0)
        action = decision_data.get("action")
        price = decision_data.get("price", 0.0)

        if action in ["accept", "counter"]:
            if price < floor_price:
                return Observation(
                    success=False,
                    error="FLOOR_PRICE_VIOLATION",
                    data={"safe_price": floor_price * 1.05}
                )

            # Check margin
            min_margin = getattr(self.settings.logic, "min_margin", 0.1)
            required_min_price = floor_price / (1 - min_margin)
            if price < required_min_price:
                return Observation(
                    success=False,
                    error="MIN_MARGIN_VIOLATION",
                    data={"safe_price": required_min_price}
                )

        return Observation(success=True)
