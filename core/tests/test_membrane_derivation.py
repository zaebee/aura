"""
The derivation travels with the Intent that was actually sent.

`outcome_gate` says which rule refused a decision. It does not say which rules
were consulted first, so on its own it cannot be replayed: two deployments could
report the same failing gate having evaluated different sets on the way there.
The gate sequence closes that, and `derivation_hash` lets a reader confirm the
sequence has not been edited before paying to replay it
(docs/DECISION_RECEIPT.md §3.4).

Nothing here is worth having if the record leaks a number, so that is asserted
against the Intent itself rather than only against the engine that built it.
"""

from unittest.mock import patch

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    Intent,
    NegotiationIntent,
    Observation,
    RWAComplianceScore,
    RWAVaultIntent,
    TradeIntent,
    ValidationScore,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.membrane.receipt import verify
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard
from eth_account import Account
from eth_account.messages import encode_typed_data

FLOOR = 1000.0


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 1000.0
    trade_risk_threshold = 0.10


def guarded_membrane() -> HiveMembrane:
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    return HiveMembrane(registry=registry)


def negotiation_context(floor_price: float = FLOOR) -> Context:
    return Context(
        metadata=make_struct(
            {"floor_price": str(floor_price), "internal_cost": "777.0"}
        )
    )


def counter_intent(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


class TestTheDerivationReachesTheIntent:
    @pytest.mark.asyncio
    async def test_an_emitted_decision_carries_the_gates_it_passed(self) -> None:
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.receipt.derivation.gate_sequence.startswith(
            "G1_PRICE_POSITIVE:pass:"
        )
        assert "G4_MARGIN_VIOLATION:pass:" in decision.receipt.derivation.gate_sequence
        assert len(decision.receipt.derivation.derivation_hash) == 64

    @pytest.mark.asyncio
    async def test_an_overridden_decision_carries_the_gate_that_stopped_it(
        self,
    ) -> None:
        """
        The override builds a fresh Intent, so the record has to be carried over
        deliberately — the same trap `identifier` and `trace` fell into.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.receipt.derivation.gate_sequence == (
            "G1_PRICE_POSITIVE:pass:price\x1fG2_FLOOR_VIOLATION:fail:price,floor_price"
        )
        assert len(decision.receipt.derivation.derivation_hash) == 64

    @pytest.mark.asyncio
    async def test_the_hash_matches_the_sequence_that_travelled(self) -> None:
        """
        The pair is redundant on purpose: a reader confirms the two agree with
        one hash compare and only then pays to replay the steps.
        """
        import hashlib

        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert (
            decision.receipt.derivation.derivation_hash
            == hashlib.sha256(
                decision.receipt.derivation.gate_sequence.encode("utf-8")
            ).hexdigest()
        )


class TestReplay:
    """
    The claim the digest makes is that someone else can re-derive it. A digest
    reproducible only inside one process is worth nothing to the party it is
    handed to.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_the_same_decision_derives_byte_identically_twice(
        self, price: float
    ) -> None:
        """
        Fresh Membrane, fresh registry, fresh guard on each run — anything that
        survived between them would be state the verifier does not have.
        """
        first = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )
        second = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )

        assert (
            first.receipt.derivation.gate_sequence
            == second.receipt.derivation.gate_sequence
        )
        assert (
            first.receipt.derivation.derivation_hash
            == second.receipt.derivation.derivation_hash
        )

    @pytest.mark.asyncio
    async def test_a_different_floor_changing_the_verdict_changes_the_digest(
        self,
    ) -> None:
        """
        The digest tracks the steps, so it moves when the steps do — here
        because a higher floor makes G2 fail where it had passed.
        """
        passing = await guarded_membrane().inspect_outbound(
            counter_intent(price=1500.0), negotiation_context(floor_price=1000.0)
        )
        failing = await guarded_membrane().inspect_outbound(
            counter_intent(price=1500.0), negotiation_context(floor_price=9000.0)
        )

        assert (
            passing.receipt.derivation.derivation_hash
            != failing.receipt.derivation.derivation_hash
        )

    @pytest.mark.asyncio
    async def test_a_different_floor_leaving_the_verdict_alone_does_not(self) -> None:
        """
        The other half of the same property, and the one that keeps the digest
        from being a value oracle: two different floors that both pass every
        gate derive identically, so the digest cannot be probed for the floor.
        """
        low = await guarded_membrane().inspect_outbound(
            counter_intent(price=5000.0), negotiation_context(floor_price=1000.0)
        )
        high = await guarded_membrane().inspect_outbound(
            counter_intent(price=5000.0), negotiation_context(floor_price=2000.0)
        )

        assert (
            low.receipt.derivation.derivation_hash
            == high.receipt.derivation.derivation_hash
        )


class TestTheIntentNeverCarriesAValue:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_no_hidden_number_appears_in_the_sequence(self, price: float) -> None:
        """
        The floor and the internal cost are the two things the Membrane spends
        its outbound path keeping off the wire. A field meant to be published
        must not put them back.
        """
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            counter_intent(price=price), negotiation_context(floor_price=FLOOR)
        )

        sequence = decision.receipt.derivation.gate_sequence
        for secret in ("1000", "777", str(price), str(int(price))):
            assert secret not in sequence


class TestAGuardThatReportsNothingUsable:
    """
    The Membrane reads the record out of whatever the guard skill reported, and
    a skill is free to report an Observation it did not fill in.

    Neither case below is reachable from `GuardSkill` today, which always
    returns both keys as strings. They are guarded because this PR moved
    `metadata.to_dict()` onto the passing path, where it had never run before —
    the failure path was the only caller until now — and because attaching a
    derivation built from junk is the exact thing the empty-record rule exists
    to prevent.
    """

    class _SilentGuard:
        """A guard protein that answers without filling in its metadata."""

        def __init__(self, observation: Observation) -> None:
            self._observation = observation

        def get_name(self) -> str:
            return "guard"

        async def execute(self, intent: str, params: dict) -> Observation:
            # The Membrane also asks this double to check the post-condition on
            # what it is about to emit. These tests are about validate_decision
            # reporting metadata the Membrane cannot use, not about psi, so
            # report a clean hold here rather than have that second question
            # decide an outcome these tests were not written to describe.
            if intent == "check_postcondition":
                return Observation(
                    success=True,
                    metadata=make_struct({"holds": True, "failed_clause": ""}),
                )
            return self._observation

    def membrane_reporting(self, observation: Observation) -> HiveMembrane:
        registry = SkillRegistry()
        registry.register("guard", self._SilentGuard(observation))
        return HiveMembrane(registry=registry)

    @pytest.mark.asyncio
    async def test_an_observation_without_metadata_does_not_take_the_guard_down(
        self,
    ) -> None:
        """
        A crash here would lose the negotiation, and it would do so inside the
        one component whose job is to never let a bad decision out.
        """
        membrane = self.membrane_reporting(Observation(success=True, metadata=None))

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.receipt.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_null_valued_record_is_not_attached_as_the_word_none(self) -> None:
        """
        `str(None)` is "None", which is truthy — so the naive read would attach a
        DecisionDerivation whose sequence is the literal text None and whose
        hash claims a derivation that never ran.
        """
        membrane = self.membrane_reporting(
            Observation(
                success=True,
                metadata=make_struct({"gate_sequence": None, "derivation_hash": None}),
            )
        )

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.derivation.gate_sequence == ""
        assert decision.receipt.derivation.derivation_hash == ""


class TestNoDeclaredGateRan:
    """
    These paths refuse or emit without consulting the rule set, so they have no
    derivation to show. Attaching an empty-string hash would be a claim that
    something was derived; leaving the field unset says plainly that nothing was.

    The Membrane's own checks — KYC, trade risk, DLP — are not declared in any
    rule set yet, so they cannot be recorded as gates without inventing ids
    nothing versions (docs/DECISION_RECEIPT.md §3.3).
    """

    @pytest.mark.asyncio
    async def test_a_kyc_refusal_shows_no_derivation(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(
                wallet_address="0xdead",
                compliance=RWAComplianceScore(kyc_passed=False),
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_REFUSE
        assert decision.receipt.derivation.gate_sequence == ""
        assert decision.receipt.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_high_risk_trade_refusal_shows_no_derivation(self) -> None:
        membrane = guarded_membrane()
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                validation_score=ValidationScore(
                    risk_score=0.9, risk_category="EXTREME"
                )
            ),
        )

        decision = await membrane.inspect_outbound(intent, negotiation_context())

        assert decision.receipt.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_a_model_reject_shows_no_derivation(self) -> None:
        """The guard is never consulted: only accept and counter put a price out."""
        membrane = guarded_membrane()

        decision = await membrane.inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_REJECT,
                negotiation=NegotiationIntent(price=0.0, message="no thanks"),
            ),
            negotiation_context(),
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.receipt.derivation.derivation_hash == ""

    @pytest.mark.asyncio
    async def test_an_unwired_membrane_shows_no_derivation(self) -> None:
        """
        No registry means no guard ran. Claiming a derivation here would be the
        worst version of the lie: a receipt asserting gates on a deployment that
        has none wired.
        """
        membrane = HiveMembrane(registry=None)

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT
        assert decision.receipt.derivation.derivation_hash == ""


class TestTheReceiptTheMembraneMints:
    """
    End-to-end: the receipt on a real emitted Intent should survive the
    verifier, which is the only claim any of this makes.
    """

    @pytest.mark.asyncio
    async def test_it_names_the_rule_set_that_judged_the_decision(self) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.ruleset_version.startswith("guard/negotiation@")

    @pytest.mark.asyncio
    async def test_a_decision_no_rule_set_judged_names_none(self) -> None:
        """
        An empty version rather than a plausible-looking default: the KYC path
        consults no rule set, and naming one would be a claim about how the
        decision was reached that is simply untrue.
        """
        decision = await guarded_membrane().inspect_outbound(
            Intent(
                action=ActionType.ACTION_TYPE_APPROVE,
                rwa_vault=RWAVaultIntent(
                    wallet_address="0xdead",
                    compliance=RWAComplianceScore(kyc_passed=False),
                ),
            ),
            negotiation_context(),
        )

        assert decision.receipt.ruleset_version == ""
        assert decision.receipt.outcome_gate == "KYC_FAILURE"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_the_minted_receipt_verifies(self, price: float) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )

        result = verify(decision.receipt)

        assert result.ok, result.failures

    @pytest.mark.asyncio
    async def test_an_override_is_visible_as_two_differing_hashes(self) -> None:
        """
        The property the claim/emission pair exists for. A reader compares two
        hex strings and knows the price they were given is the guard's, not the
        model's — without being told, and without trusting the telling.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.receipt.claim_hash != decision.receipt.emission_hash

    @pytest.mark.asyncio
    async def test_an_untouched_decision_shows_two_matching_hashes(self) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.claim_hash == decision.receipt.emission_hash

    @pytest.mark.asyncio
    async def test_the_receipt_never_carries_a_hidden_number(self) -> None:
        """
        Every field at once, not just the gate sequence: the receipt is the
        artefact meant to leave the building.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context(floor_price=FLOOR)
        )
        r = decision.receipt
        rendered = " ".join(
            [
                r.version,
                r.claim_hash,
                r.ruleset_version,
                r.emission_hash,
                r.outcome_gate,
                r.canonical_prefix,
                r.derivation.gate_sequence,
                r.derivation.derivation_hash,
            ]
        )

        for secret in ("1000", "777", "500", "1050"):
            assert secret not in rendered


class TestAContextWithNullNumbers:
    """
    A Struct round-trips a JSON null back as None, and the outbound path read
    `float(str(ctx_meta.get(...)))` — so `float("None")` raised ValueError.

    Nothing catches it. `MetabolicLoop.execute` wraps neither membrane call, so
    the exception leaves the cycle entirely and the negotiation is lost. That is
    the wrong failure for the component whose whole job is to be the thing that
    does not let a bad decision out: refusing safely is its business, crashing
    is not.
    """

    @pytest.mark.asyncio
    async def test_a_null_floor_does_not_crash_the_outbound_path(self) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0),
            Context(metadata=make_struct({"floor_price": None})),
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT

    @pytest.mark.asyncio
    async def test_a_null_cost_does_not_crash_the_outbound_path(self) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0),
            Context(
                metadata=make_struct({"floor_price": "1000.0", "internal_cost": None})
            ),
        )

        assert decision.receipt.derivation.derivation_hash != ""

    @pytest.mark.asyncio
    async def test_an_unparseable_floor_does_not_crash_either(self) -> None:
        """Same failure, different input: the guard is not a parser."""
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0),
            Context(metadata=make_struct({"floor_price": "not a number"})),
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_EMIT


class TestSigningTheReceipt:
    """
    The Membrane asks whoever holds the key to attest the receipt it just
    minted. Everything here is about what happens when that does not work.
    """

    class _Signer:
        """Stands in for the transaction protein, which owns the EVM key."""

        def __init__(self, account: object | None = None, fail: bool = False) -> None:
            self.account = account
            self.fail = fail

        def get_name(self) -> str:
            return "transaction"

        async def execute(self, intent: str, params: dict) -> Observation:
            if self.fail:
                raise RuntimeError("hardware wallet unplugged")
            payload = params["payload"]
            sig = self.account.sign_message(encode_typed_data(full_message=payload))
            return Observation(
                success=True,
                metadata=make_struct(
                    {"signer": self.account.address, "signature": sig.signature.hex()}
                ),
            )

    def membrane_with(self, signer: object | None) -> HiveMembrane:
        registry = SkillRegistry()
        guard = GuardSkill()
        guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
        registry.register(guard.get_name(), guard)
        if signer is not None:
            registry.register(signer.get_name(), signer)
        return HiveMembrane(registry=registry)

    @pytest.mark.asyncio
    async def test_a_signed_receipt_verifies_and_is_attested(self) -> None:
        account = Account.create()
        membrane = self.membrane_with(self._Signer(account))

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        result = verify(decision.receipt)
        assert result.ok, result.failures
        assert result.attested
        assert decision.receipt.signature.signer == account.address

    @pytest.mark.asyncio
    async def test_no_signer_means_an_unsigned_receipt_that_says_so(self) -> None:
        """
        Not an error. A deployment with no key still produces a usable record;
        it just cannot be attributed, and the version name is where that is
        stated rather than left for the reader to infer.
        """
        decision = await self.membrane_with(None).inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        result = verify(decision.receipt)
        assert result.ok
        assert not result.attested
        assert "UNSIGNED" in decision.receipt.version

    @pytest.mark.asyncio
    async def test_a_failing_signer_does_not_cost_the_decision(self) -> None:
        """
        The decision has already been made and is safe by the time signing is
        attempted. Losing it because a key was unreachable would trade the
        guarantee for the attestation, which is the wrong way round.
        """
        membrane = self.membrane_with(self._Signer(fail=True))

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.negotiation.price != 500.0
        assert "UNSIGNED" in decision.receipt.version

    @pytest.mark.asyncio
    async def test_signing_covers_the_emitted_price_not_the_proposed_one(self) -> None:
        """
        The attestation has to be over what was sent. Signing the model's
        proposal would attest to a document the counterparty never received.
        """
        account = Account.create()
        membrane = self.membrane_with(self._Signer(account))

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert verify(decision.receipt).attested
        assert decision.receipt.claim_hash != decision.receipt.emission_hash


class TestNothingInAttestationCanCostTheDecision:
    """
    `_attest` promises that a decision survives any failure to sign it. That
    promise should hold structurally, not because someone audited each line.

    The chain id was read outside the try block. It could not actually raise —
    `Settings.crypto` is a pydantic field with a default factory, so it is never
    absent, and `getattr(None, ..., 0)` returns the default rather than raising.
    But a property that holds only under analysis stops holding the moment
    someone edits the line, and there is nothing to catch that.
    """

    @pytest.mark.asyncio
    async def test_settings_without_crypto_still_emit_the_decision(self) -> None:
        membrane = guarded_membrane()

        class _NoCrypto:
            """Settings as a stub might supply them: no crypto section at all."""

            safety = _Safety()

        membrane.settings = _NoCrypto()

        decision = await membrane.inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.negotiation.price != 500.0

    @pytest.mark.asyncio
    async def test_a_broken_logger_does_not_cost_the_decision(self) -> None:
        """
        The same rule `_record_intervention` already follows, applied to the
        receipt log line: reporting on a decision must never take that decision
        down. A log call that raises would lose the negotiation for a sentence
        nobody was going to read at the time.
        """
        membrane = guarded_membrane()

        with patch(
            "aura_hive.hive.membrane.main.logger.info",
            side_effect=RuntimeError("log sink is gone"),
        ):
            decision = await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context()
            )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.negotiation.price != 500.0
        assert decision.receipt.canonical_prefix != ""


class TestTheReceiptLogClaimsOnlyWhatItKnows:
    """
    `attested` is a word `verify` owns: it means the signature recovered to the
    signer the receipt claims. The log line never recovers anything — it knows
    only whether a signature is attached.

    The log now carries `receipt.to_dict()` rather than a hand-picked scalar, so
    that fact is read from the document itself: betterproto omits an empty
    `signature` field from the dict rather than emitting it null, so an unsigned
    receipt's logged payload carries no `signature` key at all and a signed
    one's does. A reader checking presence, not a top-level `signed` flag this
    module used to compute, cannot claim an attestation nobody performed — the
    same overstatement `VerificationResult` separates `ok` from `attested` to
    avoid, in a cheaper place.
    """

    def logged(self, calls: list) -> dict:
        return next(kw for _, kw in calls if _ and _[0] == "membrane_receipt")

    @pytest.mark.asyncio
    async def test_an_unsigned_decision_is_not_reported_as_signed(self) -> None:
        calls: list = []
        membrane = guarded_membrane()

        with patch(
            "aura_hive.hive.membrane.main.logger.info",
            side_effect=lambda *a, **kw: calls.append((a, kw)),
        ):
            await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context()
            )

        assert "signature" not in self.logged(calls)["receipt"]

    @pytest.mark.asyncio
    async def test_a_signed_decision_is(self) -> None:
        calls: list = []
        account = Account.create()
        registry = SkillRegistry()
        guard = GuardSkill()
        guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
        registry.register(guard.get_name(), guard)
        registry.register("transaction", TestSigningTheReceipt._Signer(account))
        membrane = HiveMembrane(registry=registry)

        with patch(
            "aura_hive.hive.membrane.main.logger.info",
            side_effect=lambda *a, **kw: calls.append((a, kw)),
        ):
            await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context()
            )

        assert "signature" in self.logged(calls)["receipt"]
