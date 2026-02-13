import structlog
from typing import Any

from aura_core import Observation, SkillProtocol

from config.policy import SafetySettings

from .engine import OutputGuard, SafetyViolation
from .schema import SafePriceParams, ValidationParams, VisionValidationParams
from hive.metabolism.math import HillDampener

logger = structlog.get_logger(__name__)


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
            "validate_vision": self._validate_vision,
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
            elif "hill" in err_msg.lower():
                code = "HILL_CAP_VIOLATION"

            assert self.provider is not None
            safe_p = self.provider.calculate_safe_price(params.get("context", {}), code)
            return Observation(
                success=False,
                error=err_msg,
                metadata={"error_code": code, "safe_price": str(safe_p)},
            )
        except Exception as e:
            logger.error("guard_skill_error", error=str(e), exc_info=True)
            return Observation(success=False, error=str(e))

    async def _validate_decision(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = ValidationParams(**params)

        # 1. Standard deterministic validation (floor, margin)
        self.provider.validate_decision(p.decision, p.context)

        # 2. Hill Dampener Injection (The v0.3.0 Metamorphosis)
        # Every outbound NegotiationIntent must be validated by HillDampener.apply
        llm_price = float(p.decision.get("price", 0.0))
        bid_price = float(p.context.get("bid", 0.0))
        base_price = float(p.context.get("base_price", 0.0))

        if llm_price > 0 and bid_price > 0:
            dampened_price = HillDampener.apply(llm_price, bid_price, base_price)
            if dampened_price < llm_price:
                logger.warning(
                    "hill_cap_violation",
                    llm_price=llm_price,
                    bid=bid_price,
                    base=base_price,
                    cap=dampened_price
                )
                # We treat it as a violation to trigger the Membrane override logic
                raise SafetyViolation(f"Hill Cap Violation: price {llm_price} exceeds dampened ceiling {dampened_price}")

        return Observation(success=True)

    async def _get_safe_price(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p_safe = SafePriceParams(**params)
        price = self.provider.calculate_safe_price(p_safe.context, p_safe.reason)

        # Also apply hill dampener to safe price if it's a hill violation recovery
        if "hill" in p_safe.reason.lower():
            bid = float(p_safe.context.get("bid", 0.0))
            base = float(p_safe.context.get("base_price", 0.0))
            price = HillDampener.hill_cap(bid, base)

        return Observation(
            success=True, metadata={"safe_price": str(price)}
        )

    async def _validate_vision(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = VisionValidationParams(**params)
        self.provider.validate_vision(p.vision_result)
        return Observation(success=True)
