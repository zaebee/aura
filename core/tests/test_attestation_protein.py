"""
The protein that holds the key.

It signs a document it is handed and does not build one. The Membrane owns
what a receipt says; having one side assemble a document the other signs blind
is how the two drift into signing different things.
"""

from typing import Any

import pytest
from aura_hive.config.attestation import AttestationSettings
from aura_hive.hive.proteins.attestation.engine import AttestationEngine
from aura_hive.hive.proteins.attestation.skill import AttestationSkill
from eth_account import Account
from eth_account.messages import encode_typed_data


def a_payload(chain_id: int = 84532) -> dict[str, Any]:
    """
    The EIP-712 shape `signing_payload()` produces, built by hand here.

    The domain version is `RECEIPT_EIP712_VERSION`, which is "1" and tracks the
    EIP-712 domain rather than the receipt format — this fixture said "2" and
    taught the opposite. The engine signs whatever it is handed, so the drift
    was harmless to the assertions and precisely the kind the module docstring
    warns about: one side building a document the other signs blind.
    """
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "DecisionReceipt": [{"name": "content", "type": "string"}],
        },
        "domain": {
            "name": "AuraDecisionReceipt",
            "version": "1",
            "chainId": chain_id,
        },
        "primaryType": "DecisionReceipt",
        "message": {"content": "some-canonical-content"},
    }


def _recover(payload: dict[str, Any], signature: str) -> str:
    raw = bytes.fromhex(signature.removeprefix("0x"))
    return str(
        Account.recover_message(encode_typed_data(full_message=payload), signature=raw)
    )


class TestTheEngine:
    def test_the_signature_recovers_to_the_signer_it_reports(self) -> None:
        """
        The property, not the presence. Asserting the string is non-empty
        would pass for a signature by the wrong key.
        """
        account = Account.create()
        engine = AttestationEngine(account.key.hex())
        payload = a_payload()

        result = engine.sign(payload)

        assert _recover(payload, result["signature"]) == account.address
        assert result["signer"] == account.address

    def test_a_different_domain_produces_a_different_signature(self) -> None:
        """
        Domain separation is what stops a receipt signature being reusable as
        anything else signed by the same key.
        """
        engine = AttestationEngine(Account.create().key.hex())

        first = engine.sign(a_payload(chain_id=84532))
        second = engine.sign(a_payload(chain_id=1))

        assert first["signature"] != second["signature"]

    def test_a_key_that_signs_unrecoverably_is_refused_at_construction(self) -> None:
        """
        The all-zero key is accepted by `Account.from_key`, yields an address,
        and signs 65 bytes that no recovery accepts. It is also the canonical
        placeholder a secret template or a CI variable gets seeded with.

        Without this check such a deployment reports `attestation_signer_ready`,
        stamps receipts `AURA-RECEIPT-V2`, and every one of them fails
        `verify()` — the deployment believes it attests while the corpus is
        worthless. That is strictly worse than the unsigned state this protein
        exists to replace, because the unsigned one is honest.

        Checked by signing and recovering rather than by range-checking the
        scalar, so any degenerate key the library mishandles is caught, not
        just this one.
        """
        with pytest.raises(ValueError, match="cannot produce a recoverable"):
            AttestationEngine("0x" + "00" * 32)

    def test_the_address_is_readable_without_signing_anything(self) -> None:
        """The Cortex logs it at startup, before any decision exists."""
        account = Account.create()

        assert AttestationEngine(account.key.hex()).address == account.address


class TestTheSkill:
    @pytest.mark.asyncio
    async def test_it_signs_the_payload_it_is_given(self) -> None:
        account = Account.create()
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
        payload = a_payload()

        obs = await skill.execute("sign_receipt", {"payload": payload})

        assert obs.success
        meta = obs.metadata.to_dict()
        assert meta["signer"] == account.address
        assert _recover(payload, meta["signature"]) == account.address

    @pytest.mark.asyncio
    async def test_a_missing_payload_is_reported_not_raised(self) -> None:
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(Account.create().key.hex()))

        obs = await skill.execute("sign_receipt", {})

        assert not obs.success
        assert obs.error == "payload_missing"

    @pytest.mark.asyncio
    async def test_an_unknown_intent_is_reported_not_raised(self) -> None:
        skill = AttestationSkill()
        skill.bind(AttestationSettings(), AttestationEngine(Account.create().key.hex()))

        obs = await skill.execute("spend_money", {})

        assert not obs.success

    @pytest.mark.asyncio
    async def test_a_signing_failure_is_reported_not_raised(self) -> None:
        """
        The Membrane emits an unsigned receipt rather than losing the decision,
        so this must come back as a failed Observation, never as an exception.
        """

        class _Broken:
            address = "0x0"

            def sign(self, payload: dict[str, Any]) -> dict[str, str]:
                raise RuntimeError("hsm unreachable")

        skill = AttestationSkill()
        skill.bind(AttestationSettings(), _Broken())

        obs = await skill.execute("sign_receipt", {"payload": a_payload()})

        assert not obs.success
        assert "hsm unreachable" in (obs.error or "")

    def test_the_protein_answers_to_its_name(self) -> None:
        assert AttestationSkill().get_name() == "attestation"
        assert "sign_receipt" in AttestationSkill().get_capabilities()
