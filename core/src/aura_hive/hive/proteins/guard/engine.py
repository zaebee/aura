import hashlib
from collections.abc import Callable
from dataclasses import dataclass
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


def _numeric(mapping: dict, key: str, default: float = 0.0) -> float:
    """
    Read a number that a caller may not have supplied as one.

    Coerced once at the boundary rather than guarded inside each predicate, so
    the gates stay readable and no two of them can disagree about what a null
    means.

    Nothing crashes without this — the predicate raises, `skill.py` catches it
    into a generic Observation, and `SkillRegistry.execute` would catch it even
    if that did not. What is lost is the `error_code`, so the Membrane falls
    back to SAFETY_VIOLATION and the receipt stops naming which rule refused
    the decision. A null price reads as 0.0 and is refused by G1 as the invalid
    price it is, under its own code.
    """
    value = mapping.get(key, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("guard_unusable_numeric_input", key=key, value=repr(value))
        return default


# Separates records in the canonical sequence. ASCII unit separator: it cannot
# occur in a gate id or a premise key, so no escaping rule is needed and the
# canonical form has one fewer thing to get wrong.
_RECORD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class GateRecord:
    """One gate, as it was evaluated."""

    gate_id: str
    passed: bool
    consumes: tuple[str, ...]

    @property
    def canonical(self) -> str:
        """`G2_FLOOR_VIOLATION:fail:price,floor_price` — keys, never values."""
        verdict = "pass" if self.passed else "fail"
        return f"{self.gate_id}:{verdict}:{','.join(self.consumes)}"


@dataclass(frozen=True)
class Derivation:
    """
    The ordered record of how the guard reached its verdict.

    Publishable by construction: it names which premises each gate consulted,
    never what they were. Recording a value here would give away the floor in a
    field designed to be handed to the counterparty, undoing the invariant the
    Membrane spends its whole outbound path enforcing.
    """

    records: tuple[GateRecord, ...]
    failed_gate: str | None

    @property
    def canonical(self) -> str:
        return _RECORD_SEPARATOR.join(record.canonical for record in self.records)

    @property
    def digest(self) -> str:
        """
        SHA-256 over the canonical sequence, or empty when no gate ran.

        An empty sequence gets an empty digest rather than the hash of the empty
        string. Hashing nothing would assert a derivation that never happened —
        a verifier could reproduce the value and learn from it that some gates
        ran, which is false.
        """
        if not self.records:
            return ""
        return hashlib.sha256(self.canonical.encode("utf-8")).hexdigest()


class SafetyViolation(Exception):
    """
    Raised when a negotiation decision violates safety guardrails.

    `code` is the gate's declared code from ruleset.yaml. It exists because the
    caller used to recover the same information by searching this exception's
    message for "margin" or "floor" — which relabelled an audit trail whenever
    someone reworded a string, and which already misreported the fail-closed
    branch ("Cannot validate margin: ...") as a margin violation.
    """

    def __init__(
        self,
        message: str,
        code: str = "SAFETY_VIOLATION",
        derivation: "Derivation | None" = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        # The failure path is the raising path, so the record travels on the
        # exception. Recomputing it in the handler would mean evaluating the
        # gates twice and hoping both runs agreed.
        self.derivation = derivation


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
        self.ruleset.validate_against(set(self.gate_ids()), set(self.clause_ids()))

    # Gate id -> the predicate that decides it. The ids are the contract with
    # ruleset.yaml: `Ruleset.validate_against(gate_ids())` refuses to run if the
    # two ever drift, in either direction.
    #
    # A predicate returns True when the gate passes. It receives the decision
    # and context untouched rather than a narrowed view, because narrowing would
    # mean this table also encodes which premises each gate reads — and that is
    # already declared, once, as `consumes` in the rule set.
    def _gate_price_positive(self, decision: dict, context: dict) -> bool:
        price = _numeric(decision, "price")
        if price <= 0:
            logger.warning("invalid_offered_price", price=price)
            return False
        return True

    def _gate_floor_violation(self, decision: dict, context: dict) -> bool:
        price = _numeric(decision, "price")
        floor_price = _numeric(context, "floor_price")
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
        price = _numeric(decision, "price")
        internal_cost = _numeric(context, "internal_cost")
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

    @classmethod
    def clause_ids(cls) -> tuple[str, ...]:
        """The post-condition clauses this engine can evaluate."""
        return ("PSI_PRICE_POSITIVE", "PSI_ABOVE_FLOOR", "PSI_MIN_MARGIN")

    def _predicate(self, gate_id: str) -> Callable[[dict, dict], bool]:
        return {
            "G1_PRICE_POSITIVE": self._gate_price_positive,
            "G2_FLOOR_VIOLATION": self._gate_floor_violation,
            "G3_SETTINGS_PRESENT": self._gate_settings_present,
            "G4_MARGIN_VIOLATION": self._gate_margin_violation,
        }[gate_id]

    def evaluate(self, decision: dict, context: dict) -> Derivation:
        """
        Walk the declared gates in order, recording each, and stop at the first
        that fails.

        Only accept and counter are judged: those are the actions that put a
        price on the wire. A reject carrying a nonsense price is not a safety
        failure, and refusing it would turn the guard into a validator of
        decisions nobody acts on. Such a decision derives nothing, and says so
        with an empty record rather than a record of gates that did not run.
        """
        if decision.get("action") not in ["accept", "counter"]:
            return Derivation(records=(), failed_gate=None)

        records: list[GateRecord] = []
        for gate in self.ruleset.gates:
            passed = self._predicate(gate.id)(decision, context)
            records.append(
                GateRecord(gate_id=gate.id, passed=passed, consumes=gate.consumes)
            )
            if not passed:
                return Derivation(records=tuple(records), failed_gate=gate.id)

        return Derivation(records=tuple(records), failed_gate=None)

    def violation_for(self, derivation: Derivation) -> SafetyViolation:
        """
        Build the exception a closed-on-failure derivation implies.

        Separate from `evaluate` so a caller that needs the record on both the
        passing and failing paths can walk the gates once and decide afterwards.
        Evaluating twice would be wasteful and, worse, would rest on the two
        runs agreeing.
        """
        assert derivation.failed_gate is not None, "derivation did not fail"
        gate = {g.id: g for g in self.ruleset.gates}[derivation.failed_gate]
        return SafetyViolation(
            self._MESSAGES[gate.id], code=gate.code, derivation=derivation
        )

    def validate_decision(self, decision: dict, context: dict) -> bool:
        """Raise on the first gate that fails. `evaluate` does the walking."""
        derivation = self.evaluate(decision, context)

        if derivation.failed_gate is not None:
            raise self.violation_for(derivation)

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
        Deterministic substitute price for the one strategy the rule set declares.

        `reason` is a gate code where one fired, but not always: the Membrane
        passes FAILURE_RECOVERY when the Transformer itself blew up, and no gate
        was involved. It is unused here — transitionally: this restores the old
        margin-only formula so the module keeps compiling after the strategy
        collapse. Task 3 replaces this body with the real `safe_offer`
        computation (Decimal, ceiling, cost floor, jitter).
        """
        floor = _numeric(context, "floor_price")
        min_m = self._configured_margin()
        return float(round(floor / (1 - min_m), 2))

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
