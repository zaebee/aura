"""
"The check could not be performed" is not "the check was performed and refused".

Both refuse, and both should — a wallet whose sanctification cannot be
established must not transact. But they refuse for different reasons, and the
guard used to report them the same way on one path and differently on the other:
`_validate_transaction` treated a failed lookup as an unsanctified wallet, while
`_validate_x402_payment` twenty lines below returned a descriptive error.

An operator reading "wallet is not sanctified" goes and looks at the wallet.
When the fault is that persistence is down, that is a wrong-turn of a diagnosis
handed out by the component best placed to know better.

This is the distinction the receipt work drew between `ok` and `attested`:
nothing was wrong versus someone established something. The guard now answers it
the same way in both places.
"""

from typing import Any

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import Observation
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard


class _Safety:
    min_profit_margin = 0.10
    max_x402_payment = 5.0


class _Persistence:
    """Stands in for the protein that answers sanctification questions."""

    def __init__(self, observation: Observation) -> None:
        self._observation = observation

    def get_name(self) -> str:
        return "persistence"

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        return self._observation


def guard_talking_to(observation: Observation) -> GuardSkill:
    registry = SkillRegistry()
    registry.register("persistence", _Persistence(observation))
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    guard.inject_registry(registry)
    return guard


LOOKUP_FAILED = Observation(success=False, error="connection refused")
NOT_SANCTIFIED = Observation(success=True, metadata=make_struct({"sanctified": False}))
SANCTIFIED = Observation(success=True, metadata=make_struct({"sanctified": True}))

TRANSACTION = {
    "wallet_address": "0xabc",
    "llm_price": 100.0,
    "bid": 90.0,
    "base_price": 100.0,
}
PAYMENT = {"wallet_address": "0xabc", "amount": 1.0}


def code_of(observation: Observation) -> str:
    return str(observation.metadata.to_dict().get("error_code", ""))


class TestAFailedLookupSaysSo:
    @pytest.mark.asyncio
    async def test_a_transaction_does_not_blame_the_wallet(self) -> None:
        obs = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_transaction", TRANSACTION
        )

        assert obs.success is False
        assert code_of(obs) == "SANCTIFICATION_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_a_payment_does_not_either(self) -> None:
        obs = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_x402_payment", PAYMENT
        )

        assert obs.success is False
        assert code_of(obs) == "SANCTIFICATION_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_both_paths_report_it_identically(self) -> None:
        """
        The point of the change. The same underlying fault reaching two
        capabilities of one protein should not produce two different stories.
        """
        transaction = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_transaction", TRANSACTION
        )
        payment = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_x402_payment", PAYMENT
        )

        assert code_of(transaction) == code_of(payment)

    @pytest.mark.asyncio
    async def test_the_underlying_error_is_not_swallowed(self) -> None:
        """An operator needs the cause, not only that there was one."""
        obs = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_transaction", TRANSACTION
        )

        assert "connection refused" in obs.error


class TestARefusalStillReadsAsARefusal:
    @pytest.mark.asyncio
    async def test_an_unsanctified_wallet_is_still_named_as_such(self) -> None:
        """
        The distinction cuts both ways: a wallet that really is unsanctified
        must not be reported as an outage.
        """
        obs = await guard_talking_to(NOT_SANCTIFIED).execute(
            "validate_transaction", TRANSACTION
        )

        assert obs.success is False
        assert code_of(obs) != "SANCTIFICATION_UNAVAILABLE"
        assert "sanctified" in obs.error.lower()

    @pytest.mark.asyncio
    async def test_a_payment_from_an_unsanctified_wallet_too(self) -> None:
        obs = await guard_talking_to(NOT_SANCTIFIED).execute(
            "validate_x402_payment", PAYMENT
        )

        assert obs.success is False
        assert code_of(obs) != "SANCTIFICATION_UNAVAILABLE"


class TestNothingGetsThrough:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("capability", "params"),
        [("validate_transaction", TRANSACTION), ("validate_x402_payment", PAYMENT)],
    )
    async def test_a_failed_lookup_still_fails_closed(
        self, capability: str, params: dict[str, Any]
    ) -> None:
        """
        Naming the fault better must not soften it. A wallet whose
        sanctification cannot be established does not transact.
        """
        obs = await guard_talking_to(LOOKUP_FAILED).execute(capability, params)

        assert obs.success is False

    @pytest.mark.asyncio
    async def test_a_sanctified_wallet_still_passes(self) -> None:
        obs = await guard_talking_to(SANCTIFIED).execute(
            "validate_transaction", TRANSACTION
        )

        assert obs.success is True


class TestTheReportClaimsOnlyWhatApplies:
    """
    `execute` renders every SafetyViolation the same way, and that way was
    shaped for negotiation decisions: a substitute price and the version of the
    rule set that judged them.

    Neither applies to a wallet lookup. There is no safe price for "we could not
    check", and a consumer reading `safe_price: 0.0` could act on it; and the
    negotiation rule set did not judge this, so citing its version claims an
    audit trail that does not exist. Same rule as everywhere else in this
    series — say what happened, not what the surrounding shape expects.
    """

    @pytest.mark.asyncio
    async def test_a_lookup_failure_proposes_no_price(self) -> None:
        obs = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_transaction", TRANSACTION
        )

        assert "safe_price" not in obs.metadata.to_dict()

    @pytest.mark.asyncio
    async def test_it_does_not_cite_a_rule_set_that_did_not_judge_it(self) -> None:
        obs = await guard_talking_to(LOOKUP_FAILED).execute(
            "validate_transaction", TRANSACTION
        )

        assert "ruleset_version" not in obs.metadata.to_dict()

    @pytest.mark.asyncio
    async def test_an_unsanctified_wallet_reports_the_same_way(self) -> None:
        """Not specific to the lookup failing — no wallet check is a negotiation."""
        obs = await guard_talking_to(NOT_SANCTIFIED).execute(
            "validate_x402_payment", PAYMENT
        )

        assert "safe_price" not in obs.metadata.to_dict()

    @pytest.mark.asyncio
    async def test_a_negotiation_refusal_still_carries_both(self) -> None:
        """
        The other half: a decision the rule set really did judge keeps its
        substitute price and its rule-set version. Trimming those would lose
        what the Membrane needs to build a receipt.
        """
        guard = guard_talking_to(SANCTIFIED)

        obs = await guard.execute(
            "validate_decision",
            {
                "decision": {"action": "counter", "price": 500.0},
                "context": {"floor_price": 1000.0, "internal_cost": 500.0},
            },
        )
        meta = obs.metadata.to_dict()

        assert obs.success is False
        assert meta["error_code"] == "FLOOR_PRICE_VIOLATION"
        assert float(meta["safe_price"]) > 0
        assert meta["ruleset_version"].startswith("guard/negotiation@")
        assert meta["derivation_hash"] != ""
