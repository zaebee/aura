import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config import settings

from ._output_guard import OutputGuard, SafetyViolation

logger = logging.getLogger(__name__)

DEFAULT_MIN_MARGIN = 0.1

class GuardSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Guard Protein: Handles safety validation and safe price calculation.
    """

    def __init__(self) -> None:
        self.guard = OutputGuard()

    def get_name(self) -> str:
        return "guard"

    def get_capabilities(self) -> list[str]:
        return ["validate_decision", "get_safe_price", "sanitize_input"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent in ["validate_decision", "validate_margin", "validate_floor"]:
            try:
                decision = params.get("decision", {})
                context = params.get("context", {})
                self.guard.validate_decision(decision, context)
                return Observation(success=True)
            except SafetyViolation as e:
                error_msg = str(e)
                error_code = "SAFETY_VIOLATION"
                if "margin" in error_msg.lower():
                    error_code = "MIN_MARGIN_VIOLATION"
                elif "floor" in error_msg.lower():
                    error_code = "FLOOR_PRICE_VIOLATION"
                elif "price" in error_msg.lower():
                    error_code = "INVALID_PRICE"

                safe_price = self._calculate_safe_price(params.get("context", {}), error_code)
                return Observation(
                    success=False,
                    error=error_msg,
                    data={
                        "error_code": error_code,
                        "safe_price": safe_price
                    }
                )
            except Exception as e:
                return Observation(success=False, error=f"Validation error: {e}")

        elif intent == "get_safe_price":
            reason = params.get("reason", "")
            safe_price = self._calculate_safe_price(params.get("context", {}), reason)
            return Observation(success=True, data={"safe_price": safe_price})

        elif intent == "sanitize_input":
             return Observation(success=True, data=params.get("text", ""))

        return Observation(success=False, error=f"Unknown intent: {intent}")

    def _calculate_safe_price(self, context: dict, reason: str) -> float:
        floor_price = context.get("floor_price", 0.0)

        if "margin" in reason.lower():
            min_margin = getattr(settings.logic, "min_margin", DEFAULT_MIN_MARGIN)
            # Ensure we don't divide by zero
            if min_margin >= 1.0:
                min_margin = DEFAULT_MIN_MARGIN
            return round(floor_price / (1 - min_margin), 2)

        # Default fallback: floor + 5%
        return round(floor_price * 1.05, 2)
