"""
What the Membrane can attest about a decision, and what it cannot.

The receipt gathers into one place what the previous three steps produced —
which rules judged the decision, how they were applied, what the verdict was —
and adds the pair that makes the intervention checkable: a digest of what the
model proposed and a digest of what was actually sent. Those two differing IS
the override, stated as a fact a reader can verify rather than a claim they must
take on trust.

There are two formats. `AURA-RECEIPT-V1` carries an EIP-712 signature and can be
attributed to the agent that produced it; `AURA-RECEIPT-V0-UNSIGNED` carries
everything else and says in its own name that it carries no attestation. Separate
names rather than one name and a flag, so a consumer written against the signed
format cannot be satisfied by a downgrade.

`verify` stays explicit about what it did not check — the premise hash is still
unbuilt, and a signature attests to what the receipt says rather than to
everything a reader might want.
"""

import hashlib

import pytest
from aura_core_gen.aura.core.v1 import (
    ActionType,
    AssetIntent,
    DecisionDerivation,
    DecisionOutcome,
    Intent,
    NegotiationIntent,
    RWAVaultIntent,
    TradeIntent,
)
from aura_hive.hive.membrane.receipt import (
    RECEIPT_EIP712_DOMAIN,
    RECEIPT_VERSION,
    SIGNED_VERSION,
    _prefix,
    canonical_claim,
    claim_digest,
    mint,
    signed,
    signing_payload,
    verify,
)
from aura_hive.hive.proteins.transaction.engine import EIP712_DOMAIN_NAME
from eth_account import Account
from eth_account.messages import encode_typed_data


def counter(price: float, item: str = "htl-9931", message: str = "an offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="the model's private reasoning",
        negotiation=NegotiationIntent(
            item_identifier=item, price=price, message=message, thought="a thought"
        ),
    )


class TestTheCanonicalClaim:
    def test_it_names_the_decidable_content(self) -> None:
        assert canonical_claim(counter(price=105.0)) == (
            "action=counter;item=htl-9931;price=105.00"
        )

    def test_prose_is_excluded(self) -> None:
        """
        `reasoning`, `message` and `thought` are the model's free text. Hashing
        them would make the digest irreproducible for anyone who did not receive
        the exact string, and they are not what the decision decides.
        """
        terse = counter(price=105.0, message="hi")
        florid = counter(price=105.0, message="I have thought about this at length")
        florid.reasoning = "an entirely different explanation"

        assert canonical_claim(terse) == canonical_claim(florid)

    def test_the_price_is_formatted_to_a_fixed_precision(self) -> None:
        """
        A float rendered by repr is not stable enough to hash: 105.0 and 105.00
        and 105.000000001 must not be three different claims, and the last of
        those is what arithmetic hands you.
        """
        assert "price=105.00" in canonical_claim(counter(price=105.0))
        assert "price=105.00" in canonical_claim(counter(price=105.004))
        assert "price=0.10" in canonical_claim(counter(price=0.1))

    def test_a_different_price_is_a_different_claim(self) -> None:
        assert canonical_claim(counter(price=105.0)) != canonical_claim(
            counter(price=106.0)
        )

    def test_a_trade_names_the_trade_it_decided(self) -> None:
        """
        The first cut recorded only the shape — `action=approve;params=trade` for
        every trade there has ever been. That distinguished a trade from a
        negotiation and stopped there, which is the wrong half of the job: a
        digest of "the decision the Transformer proposed" that is identical for a
        ten-dollar trade and a nine-million-dollar one does not identify a
        decision at all.
        """
        trade = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                trade_id="t-1",
                asset_identifier="AURA",
                proposed_price=10.0,
                currency_code="USD",
            ),
        )

        assert canonical_claim(trade) == (
            "action=approve;params=trade;trade=t-1;asset=AURA;price=10.00;currency=USD"
        )

    def test_two_different_trades_do_not_hash_alike(self) -> None:
        """
        Harmless while nothing signs a receipt — anyone who can swap one onto
        another Intent can equally mint a fresh one, since `mint` holds no
        secret. It stops being harmless the moment a signature makes a receipt
        worth lifting, so the collision goes now rather than being inherited by
        the format that has something to protect.
        """
        cheap = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                trade_id="t-1", asset_identifier="A", proposed_price=10.0
            ),
        )
        dear = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(
                trade_id="t-999", asset_identifier="B", proposed_price=9_000_000.0
            ),
        )

        assert claim_digest(cheap) != claim_digest(dear)

    def test_a_vault_names_the_vault_it_decided(self) -> None:
        vault = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(
                vault_id="v-1",
                asset_identifier="DEED-7",
                appraised_value_usd=250_000.0,
                ltv_ratio=0.6,
                wallet_address="0xabc",
            ),
        )

        assert canonical_claim(vault) == (
            "action=approve;params=rwa_vault;vault=v-1;asset=DEED-7;"
            "appraised=250000.00;ltv=0.6000;wallet=0xabc"
        )

    def test_two_vaults_against_different_wallets_do_not_hash_alike(self) -> None:
        """Same collateral, different beneficiary, is a different decision."""
        mine = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(vault_id="v-1", wallet_address="0xaaa"),
        )
        theirs = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(vault_id="v-1", wallet_address="0xbbb"),
        )

        assert claim_digest(mine) != claim_digest(theirs)

    def test_a_trade_and_a_vault_still_do_not_hash_alike(self) -> None:
        """The original property, kept: the shape is still part of the claim."""
        trade = Intent(
            action=ActionType.ACTION_TYPE_APPROVE, trade=TradeIntent(trade_id="x")
        )
        vault = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            rwa_vault=RWAVaultIntent(vault_id="x"),
        )

        assert claim_digest(trade) != claim_digest(vault)

    def test_an_intent_with_no_params_records_that(self) -> None:
        """The FAILURE_RECOVERY path reaches here with a bare ERROR Intent."""
        assert (
            canonical_claim(Intent(action=ActionType.ACTION_TYPE_ERROR))
            == "action=error;params=none"
        )

    def test_trade_prose_is_excluded_like_any_other(self) -> None:
        terse = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(trade_id="t-1", reasoning="short"),
        )
        florid = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            trade=TradeIntent(trade_id="t-1", reasoning="a much longer explanation"),
        )

        assert canonical_claim(terse) == canonical_claim(florid)

    def test_the_digest_is_a_full_sha256_of_the_canonical_claim(self) -> None:
        intent = counter(price=105.0)

        assert (
            claim_digest(intent)
            == hashlib.sha256(canonical_claim(intent).encode("utf-8")).hexdigest()
        )


class TestTheInterventionIsVisible:
    """
    The property the pair exists for: a reader compares two hashes and knows
    whether what arrived is what the model produced.
    """

    def test_an_untouched_decision_hashes_the_same_both_sides(self) -> None:
        proposal = counter(price=105.0)

        receipt = mint(
            claim=proposal,
            emission=proposal,
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert receipt.claim_hash == receipt.emission_hash

    def test_an_overridden_decision_does_not(self) -> None:
        receipt = mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

        assert receipt.claim_hash != receipt.emission_hash

    def test_a_rewritten_message_alone_is_not_an_intervention_by_this_measure(
        self,
    ) -> None:
        """
        Worth stating outright, because it is a limitation rather than a bug: the
        DLP gate rewrites the message and nothing else, and prose is outside the
        claim. So a DLP-only override shows equal hashes and is visible through
        `outcome` instead. Bringing prose into the hash would cost determinism
        for every decision to catch this one case.
        """
        receipt = mint(
            claim=counter(price=105.0, message="our floor_price is 100"),
            emission=counter(price=105.0, message="I cannot disclose that"),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="DLP_BLOCK",
        )

        assert receipt.claim_hash == receipt.emission_hash
        assert receipt.outcome == DecisionOutcome.DECISION_OUTCOME_OVERRIDE


class TestTheReceiptSaysWhatItIs:
    def test_the_version_declares_itself_unsigned(self) -> None:
        """
        Not decoration. A consumer that accepts this format must not be able to
        accept it in place of a signed one, and the only thing stopping that is
        the name being different.
        """
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert receipt.version == RECEIPT_VERSION
        assert "UNSIGNED" in receipt.version

    def test_the_prefix_is_sixteen_hex_characters(self) -> None:
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        assert len(receipt.canonical_prefix) == 16
        int(receipt.canonical_prefix, 16)


class TestTheReceiptIsReproducible:
    def test_the_same_decision_mints_identically(self) -> None:
        def build() -> object:
            return mint(
                claim=counter(price=92.0),
                emission=counter(price=105.0),
                ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
                derivation=DecisionDerivation(
                    gate_sequence="G1:pass:price", derivation_hash="a" * 64
                ),
                outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
                outcome_gate="FLOOR_PRICE_VIOLATION",
            )

        assert build() == build()

    @pytest.mark.parametrize(
        "changed",
        ["ruleset_version", "outcome", "outcome_gate", "emission"],
    )
    def test_changing_any_content_field_moves_the_prefix(self, changed: str) -> None:
        base = {
            "claim": counter(price=92.0),
            "emission": counter(price=105.0),
            "ruleset_version": "guard/negotiation@1.0.0+46cc0e38ca4f895c",
            "outcome": DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            "outcome_gate": "FLOOR_PRICE_VIOLATION",
        }
        altered = dict(base)
        altered[changed] = {
            "ruleset_version": "guard/negotiation@2.0.0+0000000000000000",
            "outcome": DecisionOutcome.DECISION_OUTCOME_REFUSE,
            "outcome_gate": "MIN_MARGIN_VIOLATION",
            "emission": counter(price=999.0),
        }[changed]

        assert mint(**base).canonical_prefix != mint(**altered).canonical_prefix


class TestVerifyIsHonestAboutWhatItCannotCheck:
    def base_receipt(self) -> object:
        return mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
            derivation=DecisionDerivation(
                gate_sequence="G1_PRICE_POSITIVE:pass:price",
                derivation_hash=hashlib.sha256(
                    b"G1_PRICE_POSITIVE:pass:price"
                ).hexdigest(),
            ),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

    def test_a_well_formed_receipt_passes_every_check_it_can_run(self) -> None:
        result = verify(self.base_receipt())

        assert result.ok
        assert result.failures == ()

    def test_it_names_the_checks_it_could_not_perform(self) -> None:
        """
        The point of the whole exercise. A verifier that returns a bare "valid"
        while silently skipping the integrity check teaches its consumer to trust
        a guarantee nobody made.
        """
        result = verify(self.base_receipt())

        assert "signature" in result.unverifiable
        assert "premises" in result.unverifiable
        assert not result.attested

    def test_a_tampered_prefix_is_caught(self) -> None:
        receipt = self.base_receipt()
        receipt.canonical_prefix = "0" * 16

        result = verify(receipt)

        assert not result.ok
        assert any("prefix" in failure for failure in result.failures)

    def test_a_derivation_hash_that_does_not_match_its_sequence_is_caught(self) -> None:
        receipt = self.base_receipt()
        receipt.derivation.gate_sequence = "G9_INVENTED:pass:"

        result = verify(receipt)

        assert not result.ok
        assert any("derivation" in failure for failure in result.failures)

    def test_an_override_whose_hashes_agree_is_caught(self) -> None:
        """
        A receipt claiming the Membrane substituted a value while showing the
        emission identical to the claim is internally inconsistent — except for
        the prose-only case, which is why the check reads the gate.
        """
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

        result = verify(receipt)

        assert not result.ok
        assert any("override" in failure for failure in result.failures)

    def test_a_prose_only_override_is_not_flagged(self) -> None:
        receipt = mint(
            claim=counter(price=105.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="DLP_BLOCK",
        )

        assert verify(receipt).ok

    def test_an_emit_whose_hashes_differ_is_caught(self) -> None:
        receipt = mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            outcome=DecisionOutcome.DECISION_OUTCOME_EMIT,
            outcome_gate="",
        )

        result = verify(receipt)

        assert not result.ok
        assert any("emit" in failure for failure in result.failures)

    def test_an_unspecified_outcome_is_caught(self) -> None:
        """
        Zero is protobuf's default, so an outcome nobody set is indistinguishable
        from a field that was never written. A receipt whose central claim is
        absent should not pass for one that merely had nothing go wrong.
        """
        receipt = self.base_receipt()
        receipt.outcome = DecisionOutcome.DECISION_OUTCOME_UNSPECIFIED
        receipt.canonical_prefix = _prefix(receipt)

        result = verify(receipt)

        assert not result.ok
        assert any("unspecified" in failure for failure in result.failures)

    def test_an_unknown_format_version_is_refused_outright(self) -> None:
        """
        Refusing rather than best-effort checking. A future signed format read by
        this code would have its signature ignored, and reporting `ok` on it is
        the downgrade the version string exists to prevent.
        """
        receipt = self.base_receipt()
        receipt.version = "AURA-RECEIPT-V9-WITH-SOMETHING-NEW"

        result = verify(receipt)

        assert not result.ok
        assert any("version" in failure for failure in result.failures)


class TestTheAssetClaimAlsoNamesItsDecision:
    """
    The same collision `trade` and `rwa_vault` had. Fixing two of the three
    params types that carry outward-facing content and leaving the third is
    worse than not having noticed: it reads as a decision rather than an
    oversight.
    """

    def test_two_different_asset_decisions_do_not_hash_alike(self) -> None:
        one = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            asset=AssetIntent(asset_identifier="a-1", asset_domain="lodging"),
        )
        other = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            asset=AssetIntent(asset_identifier="a-2", asset_domain="lodging"),
        )

        assert claim_digest(one) != claim_digest(other)

    def test_the_asset_domain_is_part_of_the_claim(self) -> None:
        """The same identifier in two domains is not the same asset."""
        lodging = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            asset=AssetIntent(asset_identifier="a-1", asset_domain="lodging"),
        )
        vehicles = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            asset=AssetIntent(asset_identifier="a-1", asset_domain="vehicles"),
        )

        assert claim_digest(lodging) != claim_digest(vehicles)

    def test_it_names_the_asset_it_decided(self) -> None:
        intent = Intent(
            action=ActionType.ACTION_TYPE_APPROVE,
            asset=AssetIntent(
                asset_identifier="a-1",
                asset_domain="lodging",
                action_type=ActionType.ACTION_TYPE_ACCEPT,
            ),
        )

        assert canonical_claim(intent) == (
            "action=approve;params=asset;asset=a-1;domain=lodging;asset_action=accept"
        )


class TestSigning:
    """
    A signature is what turns this from a record into an attestation.

    It is signed with the same EVM key the agent already uses on-chain, under a
    domain of its own. Not for convenience: a signature under a key nobody can
    attribute is decoration, and key distribution is the hard part. The EVM
    identity already has an answer — a counterparty resolves the recovered
    address against the ERC-8004 registry — where a fresh signing key would have
    none.
    """

    def receipt(self) -> object:
        return mint(
            claim=counter(price=92.0),
            emission=counter(price=105.0),
            ruleset_version="guard/negotiation@1.0.0+46cc0e38ca4f895c",
            outcome=DecisionOutcome.DECISION_OUTCOME_OVERRIDE,
            outcome_gate="FLOOR_PRICE_VIOLATION",
        )

    def sign_with(self, receipt: object, account: object) -> object:
        payload = signing_payload(receipt, chain_id=84532)
        signature = account.sign_message(encode_typed_data(full_message=payload))
        return signed(
            receipt,
            signer=account.address,
            signature=signature.signature.hex(),
            chain_id=84532,
        )

    def test_the_domain_is_not_the_one_trades_are_signed_under(self) -> None:
        """
        The whole reason reusing the spending key is acceptable. Different
        domain separator means a receipt signature cannot be replayed as a trade
        authorisation, nor a trade authorisation as a receipt.
        """
        payload = signing_payload(self.receipt(), chain_id=84532)

        assert payload["domain"]["name"] == RECEIPT_EIP712_DOMAIN
        assert payload["domain"]["name"] != EIP712_DOMAIN_NAME
        # A receipt has no contract, so the field is absent rather than zeroed —
        # which makes the domain structurally different, not merely renamed.
        assert "verifyingContract" not in payload["domain"]

    def test_signing_bumps_the_version_out_of_unsigned(self) -> None:
        account = Account.create()

        attested = self.sign_with(self.receipt(), account)

        assert attested.version == SIGNED_VERSION
        assert "UNSIGNED" not in attested.version
        assert attested.signature.signer == account.address

    def test_a_signed_receipt_verifies_and_is_attested(self) -> None:
        account = Account.create()

        result = verify(self.sign_with(self.receipt(), account))

        assert result.ok, result.failures
        assert result.attested
        assert "signature" not in result.unverifiable

    def test_an_unsigned_receipt_is_still_not_attested(self) -> None:
        result = verify(self.receipt())

        assert result.ok
        assert not result.attested
        assert "signature" in result.unverifiable

    def test_a_tampered_content_field_breaks_the_signature(self) -> None:
        """
        The point of signing at all: altering what the receipt says must make it
        stop verifying, not merely mismatch a prefix anyone could recompute.
        """
        account = Account.create()
        attested = self.sign_with(self.receipt(), account)

        attested.outcome_gate = "MIN_MARGIN_VIOLATION"
        attested.canonical_prefix = _prefix(attested)  # a forger would fix this

        result = verify(attested)

        assert not result.ok
        assert any("signature" in failure for failure in result.failures)

    def test_a_signature_from_another_key_does_not_pass_as_ours(self) -> None:
        """The recovered address is compared to the one the receipt claims."""
        mine = Account.create()
        theirs = Account.create()
        attested = self.sign_with(self.receipt(), theirs)
        attested.signature.signer = mine.address

        result = verify(attested)

        assert not result.ok
        assert any("signer" in failure for failure in result.failures)

    def test_a_signed_version_with_no_signature_is_refused(self) -> None:
        """
        Claiming the signed format while carrying nothing to check is the
        downgrade the version string exists to prevent, arrived at from inside.
        """
        bare = self.receipt()
        bare.version = SIGNED_VERSION
        bare.canonical_prefix = _prefix(bare)

        result = verify(bare)

        assert not result.ok
        assert any("signature" in failure for failure in result.failures)

    def test_the_verifier_rebuilds_the_domain_from_the_receipt_alone(self) -> None:
        """
        No out-of-band configuration. A receipt only checkable by someone who
        already knows how we are configured is not much of a receipt.
        """
        account = Account.create()
        attested = self.sign_with(self.receipt(), account)

        assert attested.signature.chain_id == 84532
        assert attested.signature.domain == RECEIPT_EIP712_DOMAIN
        assert verify(attested).ok
