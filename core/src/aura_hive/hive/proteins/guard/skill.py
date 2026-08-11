from typing import Any

import structlog
from aura_core import SkillProtocol, SkillRegistry, make_struct
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.policy import SafetySettings

from .engine import Derivation, OutputGuard, SafetyViolation
from .schema import SafePriceParams, ValidationParams, VisionValidationParams

logger = structlog.get_logger(__name__)


def _derivation_fields(
    derivation: "Derivation | None", ruleset_version: str = ""
) -> dict[str, str]:
    """
    The record, flattened for Observation metadata.

    Empty strings when nothing was derived rather than omitted keys, so the
    Membrane reads the same names on every path and cannot mistake "no gate ran"
    for "the skill forgot to say".

    `ruleset_version` rides along because it answers the question the record
    raises: a sequence of gate ids means nothing without saying which rule set
    those ids belong to.
    """
    if derivation is None:
        return {
            "gate_sequence": "",
            "derivation_hash": "",
            "ruleset_version": ruleset_version,
        }
    return {
        "gate_sequence": derivation.canonical,
        "derivation_hash": derivation.digest,
        "ruleset_version": ruleset_version,
    }


class GuardSkill(
    SkillProtocol[SafetySettings, OutputGuard, dict[str, Any], Observation]
):
    """
    Guard Protein: Handles safety validation and safe price calculation.
    """

    def __init__(self) -> None:
        self.settings: SafetySettings | None = None
        self.provider: OutputGuard | None = None
        self._registry: SkillRegistry | None = None
        self._capabilities = {
            "validate_decision": self._validate_decision,
            "validate_margin": self._validate_decision,
            "validate_floor": self._validate_decision,
            "get_safe_price": self._get_safe_price,
            "validate_vision": self._validate_vision,
            "validate_transaction": self._validate_transaction,
            "validate_x402_payment": self._validate_x402_payment,
        }

    def get_name(self) -> str:
        return "guard"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: SafetySettings, provider: OutputGuard) -> None:
        self.settings = settings
        self.provider = provider

    def inject_registry(self, registry: SkillRegistry) -> None:
        self._registry = registry

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
            # The gate's own code, carried on the exception. This used to be
            # recovered by searching the message for "margin" or "floor", which
            # relabelled the audit trail on any rewording and already misfiled
            # the fail-closed branch as a margin violation.
            assert self.provider is not None

            # A violation from `validate_decision` carries the derivation that
            # produced it; nothing else does. That is the signal for whether the
            # negotiation-shaped extras apply.
            #
            # They do not apply to a wallet check. There is no safe price for
            # "we could not establish whether this wallet is sanctified", and a
            # consumer reading `safe_price: 0.0` could act on it; and citing the
            # negotiation rule set would claim an audit trail for a decision it
            # never judged. Report the code and the message, and nothing the
            # surrounding shape merely expects.
            report = {"error_code": e.code}

            if e.derivation is not None:
                # `or {}` rather than a default: a caller that passed an
                # explicit None gets the same treatment as one that passed
                # nothing. This runs inside the SafetyViolation handler, a
                # sibling of the generic `except Exception` below rather than
                # nested in it, so a raise here escapes the skill entirely.
                report["safe_price"] = str(
                    self.provider.calculate_safe_price(
                        params.get("context") or {}, e.code
                    )
                )
                report.update(
                    _derivation_fields(
                        e.derivation, self.provider.ruleset.version_string
                    )
                )

            return Observation(
                success=False, error=str(e), metadata=make_struct(report)
            )
        except Exception as e:
            logger.error("guard_skill_error", intent=intent, error=str(e))
            return Observation(success=False, error=str(e))

    async def _validate_decision(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = ValidationParams(**params)
        # Walked once. The record is wanted on both paths, and re-running the
        # gates for the failing one would rest on the two runs agreeing.
        derivation = self.provider.evaluate(p.decision, p.context)

        if derivation.failed_gate is not None:
            raise self.provider.violation_for(derivation)

        return Observation(
            success=True,
            metadata=make_struct(
                _derivation_fields(derivation, self.provider.ruleset.version_string)
            ),
        )

    async def _get_safe_price(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p_safe = SafePriceParams(**params)
        price = self.provider.calculate_safe_price(p_safe.context, p_safe.reason)
        return Observation(
            success=True,
            metadata=make_struct({"safe_price": str(price)}),
        )

    async def _validate_vision(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = VisionValidationParams(**params)
        self.provider.validate_vision(p.vision_result)
        return Observation(success=True)

    async def _wallet_is_sanctified(self, wallet_address: str) -> bool:
        """
        Ask persistence whether a wallet is sanctified.

        Raises when the question could not be answered, rather than returning
        False. Both outcomes refuse — a wallet whose sanctification cannot be
        established must not transact — but they refuse for different reasons,
        and reporting a lookup failure as "not sanctified" sends an operator to
        look at the wallet when the fault is that persistence is down.

        This is the distinction the receipt work drew between `ok` and
        `attested`: nothing was wrong versus something was established. Both
        call sites go through here so the same fault cannot produce two
        different stories from one protein.
        """
        assert self._registry is not None, (
            "registry not injected — call inject_registry() first"
        )
        observation = await self._registry.execute(
            "persistence", "is_wallet_sanctified", {"wallet_address": wallet_address}
        )

        if not observation.success:
            logger.error(
                "sanctification_lookup_failed",
                wallet=wallet_address,
                error=observation.error,
            )
            raise SafetyViolation(
                f"Could not establish whether wallet {wallet_address!r} is "
                f"sanctified: {observation.error}",
                code="SANCTIFICATION_UNAVAILABLE",
            )

        return bool(observation.metadata.to_dict().get("sanctified", False))

    async def _validate_transaction(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        assert self._registry is not None, (
            "registry not injected — call inject_registry() first"
        )
        wallet_address = params.get("wallet_address", "")
        is_sanctified = await self._wallet_is_sanctified(wallet_address)
        safe_price = self.provider.validate_transaction(
            wallet_address=wallet_address,
            llm_price=params.get("llm_price", 0.0),
            bid=params.get("bid", 0.0),
            base_price=params.get("base_price", 0.0),
            is_sanctified=is_sanctified,
        )
        return Observation(
            success=True,
            metadata=make_struct({"safe_price": safe_price}),
        )

    async def _validate_x402_payment(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        assert self._registry is not None, (
            "registry not injected — call inject_registry() first"
        )
        wallet_address = params.get("wallet_address", "")
        amount = float(params.get("amount", 0.0))
        is_sanctified = await self._wallet_is_sanctified(wallet_address)
        self.provider.validate_x402_payment(
            wallet_address=wallet_address,
            amount=amount,
            is_sanctified=is_sanctified,
        )
        return Observation(success=True)
