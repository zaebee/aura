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

import re
from unittest.mock import patch

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionOutcome,
    HiveContextData,
    Intent,
    NegotiationIntent,
    NegotiationOffer,
    Observation,
    RWAComplianceScore,
    RWAVaultIntent,
    TradeIntent,
    ValidationScore,
)
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.membrane.receipt import canonical_claim, verify
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


def negotiation_context(floor_price: float = FLOOR, currency_code: str = "") -> Context:
    return Context(
        metadata=make_struct(
            {"floor_price": str(floor_price), "internal_cost": "777.0"}
        ),
        hive=HiveContextData(offer=NegotiationOffer(currency_code=currency_code)),
    )


# The message that trips the Membrane's DLP check. Ordinary traffic: the model
# explaining itself with the word it is not allowed to say.
LEAKING_MESSAGE = "my floor_price is 1000, so I can't go lower"


def counter_intent(price: float, message: str = "Here is my offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message=message),
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

        The outcome is UNAVAILABLE rather than EMIT because the post-condition
        could not be evaluated either — the same absence, read honestly at both
        ends. Nothing is emitted, and nothing is claimed about how.
        """
        membrane = HiveMembrane(registry=None)

        decision = await membrane.inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
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
    @pytest.mark.parametrize("message", ["Here is my offer", LEAKING_MESSAGE])
    async def test_the_minted_receipt_verifies(
        self, price: float, message: str
    ) -> None:
        """
        Parametrised over the MESSAGE as well as the price, and that second
        parameter is the whole point.

        It was price-only, so no test in the suite ever ran `verify()` over a
        receipt the Membrane minted for a decision whose message tripped DLP.
        At (500.0, LEAKING_MESSAGE) the DLP block recorded `scope="prose"` and
        the floor gate then substituted the price, so the digests differed and
        the verifier refused a receipt the Membrane had just produced —
        `make verify-receipts` exited 1 on ordinary traffic. Two tests asserted
        the opposite halves of that and both passed, because neither of them
        was this one.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=price, message=message), negotiation_context()
        )

        result = verify(decision.receipt)

        assert result.ok, result.failures

    @pytest.mark.asyncio
    async def test_a_dlp_block_that_also_moves_the_price_is_scoped_to_value(
        self,
    ) -> None:
        """
        `override_scope` answers "did the decidable content change", not "what
        did the gate named in `outcome_gate` touch". Both interventions ran
        here; the price moved; the answer is "value".

        Scoping it to the winning gate instead gave "prose" beside two
        differing digests — the contradiction above, stated as a field.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0, message=LEAKING_MESSAGE),
            negotiation_context(),
        )

        assert decision.receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE
        assert decision.receipt.outcome_gate == "DLP_BLOCK"
        assert decision.receipt.override_scope == "value"
        assert decision.receipt.claim_hash != decision.receipt.emission_hash


class TestTheCurrencyReachesTheClaim:
    """
    Nothing asserted a currency through the Membrane at all.

    Task 9 stamped `currency_code` from the Context onto the claim, and the bug
    it found on the way — the DLP block rebuilding a NegotiationIntent from a
    field list that omitted the currency — was caught by hand-tracing, not by a
    test. Every `NegotiationOffer` fixture in the suite left `currency_code`
    unset, so the entire class had zero coverage and a regression would have
    been invisible on all four outbound shapes.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("price", "message"),
        [
            (2000.0, "Here is my offer"),  # emitted untouched
            (500.0, "Here is my offer"),  # price substituted
            (2000.0, LEAKING_MESSAGE),  # prose sanitised
            (500.0, LEAKING_MESSAGE),  # both
        ],
    )
    async def test_every_outbound_path_keeps_the_denomination(
        self, price: float, message: str
    ) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=price, message=message),
            negotiation_context(currency_code="JPY"),
        )

        assert decision.negotiation.currency_code == "JPY"
        assert "currency=JPY" in canonical_claim(decision)
        assert verify(decision.receipt).ok

    @pytest.mark.asyncio
    async def test_the_substitute_keeps_the_item_it_is_substituting_for(
        self,
    ) -> None:
        """
        The hand-built replacement carried neither the item nor the currency, so
        a JPY negotiation emitted `action=counter;item=;price=111.12;currency=`
        — two fields disappearing from a claim that were never in question, and
        a reader diffing claim against emission seeing more changed than did.
        """
        intent = counter_intent(price=500.0)
        intent.negotiation.item_identifier = "sku-9"

        decision = await guarded_membrane().inspect_outbound(
            intent, negotiation_context(currency_code="JPY")
        )

        assert decision.negotiation.item_identifier == "sku-9"
        assert "item=sku-9" in canonical_claim(decision)
        assert "currency=JPY" in canonical_claim(decision)

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

        Split by what each field IS. A substring search only means something
        over a field that could carry a value; over a uniform digest it is a
        coin flip. `canonical_prefix` is 16 hex characters, so it contains
        "500" or "777" by chance about **0.7% of the time** — this assertion
        used to include it and failed at roughly that rate, indistinguishably
        from a real leak. The digests get a shape check instead, which is the
        stronger claim anyway: a field that is structurally 64 hex characters
        cannot carry a price whatever the price is.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context(floor_price=FLOOR)
        )
        r = decision.receipt
        rendered = " ".join(
            [
                r.version,
                r.ruleset_version,
                r.outcome_gate,
                r.override_scope,
                r.derivation.gate_sequence,
            ]
        )

        for secret in ("1000", "777", "500", "1050"):
            assert secret not in rendered

        assert re.fullmatch(r"[0-9a-f]{64}", r.claim_hash)
        assert re.fullmatch(r"[0-9a-f]{64}", r.emission_hash)
        assert re.fullmatch(r"[0-9a-f]{64}", r.derivation.derivation_hash)
        assert re.fullmatch(r"[0-9a-f]{16}", r.canonical_prefix)


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
        """
        Stands in for the attestation protein, which owns the signing key.

        Named `transaction` until the key moved out of the payments protein.
        These tests were the only coverage the Membrane's signing hop had, and
        they were coupled to it by the protein's NAME rather than by the
        capability, which is why a search for `sign_receipt` did not find them.
        """

        def __init__(self, account: object | None = None, fail: bool = False) -> None:
            self.account = account
            self.fail = fail

        def get_name(self) -> str:
            return "attestation"

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
        registry.register("attestation", TestSigningTheReceipt._Signer(account))
        membrane = HiveMembrane(registry=registry)

        with patch(
            "aura_hive.hive.membrane.main.logger.info",
            side_effect=lambda *a, **kw: calls.append((a, kw)),
        ):
            await membrane.inspect_outbound(
                counter_intent(price=500.0), negotiation_context()
            )

        assert "signature" in self.logged(calls)["receipt"]


class TestTheReceiptNamesTheDecisionItDescribes:
    """
    `decision_id` was EMPTY on every production receipt.

    Nothing on the negotiation path ever assigned `Intent.identifier`, so the
    signature covered an empty string — attesting the field's absence. V2 exists
    because binding that is not signed is decorative, and the receipt module
    sells the bump on exactly this field: without it a receipt is about a SHAPE
    of decision, and two deals for the same item at the same price produced
    byte-identical receipts, signature included.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("price", [500.0, 2000.0])
    async def test_an_emitted_decision_is_named(self, price: float) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=price), negotiation_context()
        )

        assert decision.receipt.decision_id
        assert decision.receipt.decision_id == decision.identifier

    @pytest.mark.asyncio
    async def test_an_upstream_identifier_is_not_overwritten(self) -> None:
        """
        Assigned only when absent. If a producer names its own decision, that
        name is what an auditor will be reconciling against.
        """
        intent = counter_intent(price=2000.0)
        intent.identifier = "decision-44"

        decision = await guarded_membrane().inspect_outbound(
            intent, negotiation_context()
        )

        assert decision.receipt.decision_id == "decision-44"

    @pytest.mark.asyncio
    async def test_two_identical_decisions_get_different_receipts(self) -> None:
        """
        The property the field exists for, stated as a test rather than as a
        docstring: same item, same price, same everything the model decided.
        """
        first = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )
        second = await guarded_membrane().inspect_outbound(
            counter_intent(price=2000.0), negotiation_context()
        )

        assert first.receipt.claim_hash == second.receipt.claim_hash
        assert first.receipt.canonical_prefix != second.receipt.canonical_prefix


class TestTheDisputeToken:
    @pytest.mark.asyncio
    async def test_every_emission_carries_one(self) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )

        assert decision.dispute_token

    @pytest.mark.asyncio
    async def test_a_refusal_carries_one_too(self) -> None:
        """A rejection is exactly as disputable as a counter."""
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

        assert decision.dispute_token

    @pytest.mark.asyncio
    async def test_it_is_not_derived_from_the_receipt(self) -> None:
        """
        The property that makes it safe to hand over. The canonical prefix was
        invertible by enumeration — 7.3M SHA-256 recovered the model's proposed
        price and the gate that fired. A random UUID has no preimage, so there
        is nothing in it to enumerate toward.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context()
        )
        token = decision.dispute_token

        assert token not in str(decision.receipt.to_dict())
        assert token != decision.receipt.canonical_prefix
        assert token != decision.receipt.decision_id

    @pytest.mark.asyncio
    async def test_two_decisions_in_one_session_get_different_tokens(self) -> None:
        """
        Per decision, not per session. `session_token` already names the session
        and already reaches the client; it cannot cite one round of a
        negotiation, which is what a dispute is about.
        """
        membrane = guarded_membrane()
        context = negotiation_context()

        first = await membrane.inspect_outbound(counter_intent(price=2000.0), context)
        second = await membrane.inspect_outbound(counter_intent(price=2000.0), context)

        assert first.dispute_token != second.dispute_token


class TestThePriceIsQuotedInTheCurrencyItIsIn:
    """
    Both counterparty-facing messages hardcoded a `$`.

    The branch carries `currency_code` into the claim precisely because the
    denomination is a property of the request that nothing decided — and then
    told the counterparty a JPY deal was `$111.12`. The structured field said
    one thing and the prose beside it said another, on the one path where the
    Membrane, not the model, is writing the words.

    The message is not part of the canonical claim, so nothing here moves a
    digest.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("price", "message"),
        [
            (500.0, "Here is my offer"),  # substituted: the override's message
            (2000.0, LEAKING_MESSAGE),  # sanitised: the DLP block's message
            (500.0, LEAKING_MESSAGE),  # both
        ],
    )
    async def test_no_path_quotes_a_dollar_sign_for_a_yen_deal(
        self, price: float, message: str
    ) -> None:
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=price, message=message),
            negotiation_context(currency_code="JPY"),
        )

        emitted = decision.negotiation.message
        assert "$" not in emitted, emitted
        assert "JPY" in emitted, emitted

    @pytest.mark.asyncio
    async def test_an_unstated_denomination_quotes_a_bare_number(self) -> None:
        """
        Two call sites legitimately have no source for a currency and pass the
        empty string (§3.2). A bare number is the honest rendering; the naive
        f-string leaves a trailing space before the full stop.
        """
        decision = await guarded_membrane().inspect_outbound(
            counter_intent(price=500.0), negotiation_context(currency_code="")
        )

        emitted = decision.negotiation.message
        assert " ." not in emitted, emitted
        assert "$" not in emitted, emitted
