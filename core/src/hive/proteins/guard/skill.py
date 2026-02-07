import logging
from typing import Any

from aura_core import Observation, SkillProtocol

from config.policy import SafetySettings

from .engine import OutputGuard, SafetyViolation
from .schema import SafePriceParams, ValidationParams

logger = logging.getLogger(__name__)


class GuardSkill(
    SkillProtocol[SafetySettings, OutputGuard, dict[str, Any], Observation]
):
    """
    Guard Protein: Handles safety validation and safe price calculation.
    """

    def __init__(self) -> None:
        self.settings: SafetySettings | None = None
        self.provider: OutputGuard | None = None
        self._capabilities = {
            "validate_decision": self._validate_decision,
            "validate_margin": self._validate_decision,
            "validate_floor": self._validate_decision,
            "get_safe_price": self._get_safe_price,
        }

    def get_name(self) -> str:
        return "guard"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: SafetySettings, provider: OutputGuard) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except SafetyViolation as e:
            err_msg = str(e)
            code = "SAFETY_VIOLATION"
            if "margin" in err_msg.lower():
                code = "MIN_MARGIN_VIOLATION"
            elif "floor" in err_msg.lower():
                code = "FLOOR_PRICE_VIOLATION"

            assert self.provider is not None
            safe_p = self.provider.calculate_safe_price(params.get("context", {}), code)
            return Observation(
                success=False,
                error=err_msg,
                data={"error_code": code, "safe_price": safe_p},
            )
        except Exception as e:
            logger.error(f"Guard skill error: {e}")
            return Observation(success=False, error=str(e))

    async def _validate_decision(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = ValidationParams(**params)
        self.provider.validate_decision(p.decision, p.context)
        return Observation(success=True)

    async def _get_safe_price(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p_safe = SafePriceParams(**params)
        price = self.provider.calculate_safe_price(p_safe.context, p_safe.reason)
        return Observation(success=True, data={"safe_price": price})
