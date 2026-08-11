from collections.abc import Callable
from typing import Any

import structlog

from aura_hive.hive.metabolism.math import HillDampener

from .ruleset import Ruleset, load_ruleset

logger = structlog.get_logger(__name__)

# Markup applied to the floor when a gate asks for the `floor_markup` strategy.
# Not operator-tunable: unlike min_profit_margin this is the shape of the
# fallback rather than a policy dial, so it belongs with the rules.
_FLOOR_MARKUP = 1.05

# Used when the configured margin cannot be read or is out of range. Matches
# the default on SafetySettings, so a deployment that loses its setting behaves
# like one that never overrode it.
_DEFAULT_MARGIN = 0.1


class SafetyViolation(Exception):
    """
    Raised when a negotiation decision violates safety guardrails.

    `code` is the gate's declared code from ruleset.yaml. It exists because the
    caller used to recover the same information by searching this exception's
    message for "margin" or "floor" — which relabelled an audit trail whenever
    someone reworded a string, and which already misreported the fail-closed
    branch ("Cannot validate margin: ...") as a margin violation.
    """

    def __init__(self, message: str, code: str = "SAFETY_VIOLATION") -> None:
        super().__init__(message)
        self.code = code


class OutputGuard:
    """
    Deterministic safety layer for Aura Core.
    Protects against economic hallucinations and floor price breaches.
    (The "Greedy Merchant" fix)
    """

    def __init__(self, safety_settings: Any = None, ruleset: Ruleset | None = None):
        self.settings = safety_settings
        self.ruleset = ruleset or load_ruleset()

        # Refuse to run against a rule set that does not describe this engine.
        # Doing it here rather than at import time means a bad rule set fails
        # where it can be attributed, and a test can supply its own.
        self.ruleset.validate_against(set(self.gate_ids()))

        self._safe_price_strategies = {
            gate.code: gate.safe_price for gate in self.ruleset.gates
        }

    # Gate id -> the predicate that decides it. The ids are the contract with
    # ruleset.yaml: `Ruleset.validate_against(gate_ids())` refuses to run if the
    # two ever drift, in either direction.
    #
    # A predicate returns True when the gate passes. It receives the decision
    # and context untouched rather than a narrowed view, because narrowing would
    # mean this table also encodes which premises each gate reads — and that is
    # already declared, once, as `consumes` in the rule set.
    def _gate_price_positive(self, decision: dict, context: dict) -> bool:
        price = decision.get("price", 0.0)
        if price <= 0:
            logger.warning("invalid_offered_price", price=price)
            return False
        return True

    def _gate_floor_violation(self, decision: dict, context: dict) -> bool:
        price = decision.get("price", 0.0)
        floor_price = context.get("floor_price", 0.0)
        if price < floor_price:
            logger.warning(
                "safety_floor_violation",
                action=decision.get("action"),
                offered_price=price,
                floor_price=floor_price,
            )
            return False
        return True

    def _gate_settings_present(self, decision: dict, context: dict) -> bool:
        # DNA Rule: Safety Guard must "Fail-Closed" if misconfigured.
        #
        # "Present but incomplete" is misconfiguration too. Checking only that
        # settings exist let an object without the field through to G4, where
        # the AttributeError was swallowed into a generic SAFETY_VIOLATION —
        # losing the fail-closed reason this gate exists to report.
        if not self.settings:
            logger.error("guard_settings_missing_fail_closed")
            return False
        if getattr(self.settings, "min_profit_margin", None) is None:
            logger.error("guard_margin_setting_missing_fail_closed")
            return False
        return True

    def _gate_margin_violation(self, decision: dict, context: dict) -> bool:
        price = decision.get("price", 0.0)
        internal_cost = context.get("internal_cost", 0.0)
        margin = (price - internal_cost) / price if price > 0 else 0

        # Reached only after G3_SETTINGS_PRESENT passed, so settings are here.
        min_margin = self.settings.min_profit_margin
        if margin < min_margin:
            logger.warning(
                "safety_margin_violation",
                offered_price=price,
                internal_cost=internal_cost,
                margin=margin,
                min_margin=min_margin,
            )
            return False
        return True

    _MESSAGES = {
        "G1_PRICE_POSITIVE": "Invalid offered price",
        "G2_FLOOR_VIOLATION": "Metabolic Leakage: Amount below floor price",
        "G3_SETTINGS_PRESENT": "Cannot validate margin: safety settings not provided.",
        "G4_MARGIN_VIOLATION": "Minimum profit margin violation",
    }

    @classmethod
    def gate_ids(cls) -> tuple[str, ...]:
        """The gates this engine can evaluate, for cross-checking the rule set."""
        return tuple(cls._MESSAGES)

    def _predicate(self, gate_id: str) -> Callable[[dict, dict], bool]:
        return {
            "G1_PRICE_POSITIVE": self._gate_price_positive,
            "G2_FLOOR_VIOLATION": self._gate_floor_violation,
            "G3_SETTINGS_PRESENT": self._gate_settings_present,
            "G4_MARGIN_VIOLATION": self._gate_margin_violation,
        }[gate_id]

    def validate_decision(self, decision: dict, context: dict) -> bool:
        """
        Walk the declared gates in order and raise on the first that fails.

        Only accept and counter are judged: those are the actions that put a
        price on the wire. A reject carrying a nonsense price is not a safety
        failure, and refusing it would turn the guard into a validator of
        decisions nobody acts on.
        """
        if decision.get("action") not in ["accept", "counter"]:
            return True

        for gate in self.ruleset.gates:
            if not self._predicate(gate.id)(decision, context):
                raise SafetyViolation(self._MESSAGES[gate.id], code=gate.code)

        return True

    def _configured_margin(self) -> float:
        """
        The configured minimum margin, clamped to a range that keeps
        floor/(1-m) at or above the floor.

        A margin at or above 1.0 makes the formula undefined or negative. A
        margin below 0.0 is worse and was not caught before: floor/(1-(-0.5))
        is floor/1.5, so a floor of 1000 came back as a "safe" price of 666.67.
        `min_profit_margin` is env-configurable with no lower bound declared, so
        that is one operator typo away, and the substitute price exists
        precisely to be the thing that cannot undercut the floor.

        This is also reached without any gate having run — the Membrane calls
        `calculate_safe_price` directly on FAILURE_RECOVERY — so a bad setting
        cannot be assumed to have been caught upstream.
        """
        if self.settings is None:
            return _DEFAULT_MARGIN

        raw = getattr(self.settings, "min_profit_margin", None)
        if raw is None:
            return _DEFAULT_MARGIN

        try:
            margin = float(raw)
        except (TypeError, ValueError):
            logger.error("guard_margin_setting_unreadable_using_default", raw=raw)
            return _DEFAULT_MARGIN

        if not 0.0 <= margin < 1.0:
            logger.error("guard_margin_setting_out_of_range", margin=margin)
            return _DEFAULT_MARGIN

        return margin

    def calculate_safe_price(self, context: dict, reason: str) -> float:
        """
        Deterministic substitute price, by the strategy the firing gate declared.

        `reason` is a gate code where one fired, but not always: the Membrane
        passes FAILURE_RECOVERY when the Transformer itself blew up, and no gate
        was involved. Anything the rule set does not name gets the floor markup.
        """
        floor = float(context.get("floor_price", 0.0))
        strategy = self._safe_price_strategies.get(reason, "floor_markup")

        if strategy == "margin":
            min_m = self._configured_margin()
            return float(round(floor / (1 - min_m), 2))

        return float(round(floor * _FLOOR_MARKUP, 2))

    def validate_transaction(
        self,
        wallet_address: str,
        llm_price: float,
        bid: float,
        base_price: float,
        is_sanctified: bool,
    ) -> float:
        """Validate a transaction: require sanctified wallet, apply Hill dampening ceiling."""
        if not is_sanctified:
            raise SafetyViolation(f"Wallet {wallet_address!r} is not sanctified")
        ceiling = HillDampener.hill_cap(bid, base_price)
        return min(llm_price, ceiling)

    def validate_x402_payment(
        self,
        wallet_address: str,
        amount: float,
        is_sanctified: bool,
    ) -> None:
        """Validate an autonomous x402 payment: require sanctified wallet and spending cap."""
        if not self.settings:
            logger.error("guard_settings_missing_fail_closed")
            raise SafetyViolation(
                "Cannot validate x402 payment: safety settings not provided."
            )
        if not is_sanctified:
            raise SafetyViolation(
                f"x402 recipient {wallet_address!r} is not sanctified"
            )
        max_payment_config = getattr(self.settings, "max_x402_payment", None)
        if max_payment_config is None:
            logger.warning("max_x402_payment_not_configured", fallback=5.0)
            max_payment = 5.0
        else:
            max_payment = float(max_payment_config)
        if amount > max_payment:
            raise SafetyViolation(
                f"x402 amount {amount} exceeds spending cap {max_payment}"
            )

    def validate_vision(self, vision_result: dict) -> bool:
        """
        Validate VisionSkill output.
        Checks for confidence score and required fields.
        """
        if not vision_result:
            logger.warning("vision_validation_empty")
            raise SafetyViolation("Vision result is empty")

        if "error" in vision_result:
            logger.warning(
                "vision_validation_error_present", error=vision_result["error"]
            )
            raise SafetyViolation(
                f"Vision skill reported error: {vision_result['error']}"
            )

        # Required fields check
        required_fields = ["make", "model", "year", "confidence_score"]
        for field in required_fields:
            if field not in vision_result:
                logger.warning("vision_validation_missing_field", field=field)
                raise SafetyViolation(f"Vision result missing required field: {field}")

        # Confidence threshold check
        confidence = vision_result.get("confidence_score", 0.0)
        if confidence < 0.7:
            logger.warning("vision_validation_low_confidence", confidence=confidence)
            raise SafetyViolation("Vision identification confidence too low")

        return True
