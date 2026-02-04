from typing import Any

from aura_core import Observation, SkillProtocol
from config import get_settings
from ._output_guard import OutputGuard, SafetyViolation


class GuardSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Guard Protein: Encapsulates safety validation and guardrails.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.output_guard = OutputGuard()

    def get_name(self) -> str:
        return "guard"

    def get_capabilities(self) -> list[str]:
        return ["validate_margin", "validate_floor", "sanitize_input", "validate_decision"]

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        match intent:
            case "sanitize_input":
                return self._sanitize_input(params.get("signal"))
            case "validate_decision":
                return self._validate_decision(params.get("decision"), params.get("context"))

        return Observation(success=False, error=f"Unknown intent: {intent}")

    def _sanitize_input(self, signal: Any) -> Observation:
        injection_patterns = [
            "ignore all previous instructions",
            "system override",
            "you are now",
        ]

        if hasattr(signal, "item_id") and isinstance(signal.item_id, str):
            for pattern in injection_patterns:
                if pattern in signal.item_id.lower():
                    signal.item_id = "INVALID_ID_POTENTIAL_INJECTION"
                    break

        if hasattr(signal, "agent") and hasattr(signal.agent, "did") and isinstance(signal.agent.did, str):
            for pattern in injection_patterns:
                if pattern in signal.agent.did.lower():
                    signal.agent.did = "REDACTED"
                    break

        return Observation(success=True, data=signal)

    def _validate_decision(self, decision_data: dict[str, Any], context_data: dict[str, Any]) -> Observation:
        try:
            # Ensure internal_cost is present for OutputGuard's margin calculation
            if "internal_cost" not in context_data:
                floor_price = context_data.get("floor_price", 0.0)
                context_data["internal_cost"] = floor_price * 0.8 # Fallback heuristic

            self.output_guard.validate_decision(decision_data, context_data)
            return Observation(success=True)
        except SafetyViolation as e:
            floor_price = context_data.get("floor_price", 0.0)
            return Observation(
                success=False,
                error=str(e),
                data={"safe_price": floor_price * 1.05}
            )
        except Exception as e:
            return Observation(success=False, error=str(e))
