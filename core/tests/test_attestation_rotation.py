"""
Rotating the key must not invalidate what the old key signed.

This is the premise the whole design rests on: verifying a past signature needs
only the address it recovers to, never the private key. If it were false,
signing before a consumer exists would be worthless, because the key would have
to outlive the gap — and a lost key would take the corpus with it.

A characterisation test rather than a red-green cycle. It pins a property the
design claims; if it fails, the design is wrong and the test must not be
adjusted to match.
"""

from typing import Any
from unittest.mock import patch

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionReceipt,
    HiveContextData,
    Intent,
    NegotiationIntent,
)
from aura_hive.config.attestation import AttestationSettings
from aura_hive.config.policy import SafetySettings
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.membrane.receipt import signing_payload, verify
from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard
from eth_account import Account
from eth_account.messages import encode_typed_data


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


class _Settings:
    def __init__(self, chain_id: int) -> None:
        self.attestation = AttestationSettings(chain_id=chain_id)
        self.safety = SafetySettings()


async def mint(account: Any, chain_id: int) -> DecisionReceipt:
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    skill = AttestationSkill()
    skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
    registry.register("attestation", skill)
    membrane = HiveMembrane(registry=registry)
    membrane.settings = _Settings(chain_id)

    decision = await membrane.inspect_outbound(
        Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            reasoning="LLM reasoning",
            negotiation=NegotiationIntent(price=2000.0, message="Here is my offer"),
        ),
        Context(
            metadata=make_struct({"floor_price": "1000.0", "internal_cost": "777.0"}),
            hive=HiveContextData(request_id="req-rotate"),
        ),
    )
    return decision.receipt


def verifies(receipt: DecisionReceipt) -> bool:
    """
    Recovery only — no private key is involved, which is the whole point.

    Every domain field comes from the receipt, matching what `_check_signature`
    does. Passing only `chain_id` and letting name and version fall back to the
    module constants is the exact pattern this branch removed from production,
    and a helper is what the next reader copies.
    """
    payload = signing_payload(
        receipt,
        chain_id=receipt.signature.chain_id,
        domain=receipt.signature.domain,
        domain_version=receipt.signature.domain_version,
    )
    raw = bytes.fromhex(receipt.signature.signature.removeprefix("0x"))
    recovered = Account.recover_message(
        encode_typed_data(full_message=payload), signature=raw
    )
    return bool(recovered == receipt.signature.signer)


@pytest.mark.asyncio
async def test_an_old_receipt_still_verifies_after_the_domain_constants_move() -> None:
    """
    The receipt records `domain` and `domain_version`, and `verify()` must read
    them back rather than rebuilding the domain from whatever the module
    constants say today.

    Otherwise the two fields are decoration: bump `RECEIPT_EIP712_VERSION` —
    the tidy-up the settings comment warns about for `chain_id` — and every
    receipt signed before the bump is reported not as a domain mismatch but as
    a **forgery**, because recovery under the new domain yields a different
    address than the one the receipt claims. That is the worst failure mode
    available: the verifier accusing an honest record.

    Reading the fields back is safe. A forger who edits them changes the
    document being recovered, so the recovered address stops matching the
    `signer` the receipt claims, and the existing check fails them.
    """
    from aura_hive.hive.membrane import receipt as receipt_module

    account = Account.create()
    old_receipt = await mint(account, chain_id=84532)
    assert verify(old_receipt).ok

    with patch.object(receipt_module, "RECEIPT_EIP712_VERSION", "9"):
        result = verify(old_receipt)

    assert result.ok, result.failures


@pytest.mark.asyncio
async def test_editing_the_recorded_domain_does_not_forge_a_receipt() -> None:
    """
    The other half of reading the domain out of the receipt.

    If the fields told the verifier whom to trust, this would be a hole. They
    tell it which document to reconstruct: editing them changes the message
    recovered, so the recovered address stops matching the `signer` the receipt
    still claims, and the existing signer check refuses it.

    The boundary of what this proves, so nobody cites it for more: an attacker
    who edits the domain **and** rewrites `signer` to whatever the edited
    payload now recovers to passes `verify()`. That was equally true before
    this change — `verify()` checks that a signature is the claimed signer's,
    never that the claimed signer is ours. Attribution is the signers file, and
    `verify()` is not tamper-evidence for the document as a whole.
    """
    receipt = await mint(Account.create(), chain_id=84532)
    assert verify(receipt).ok

    receipt.signature.domain = "SomeOtherDomain"

    result = verify(receipt)

    assert not result.ok
    assert any("recovers to" in failure for failure in result.failures), result.failures


@pytest.mark.asyncio
async def test_an_old_receipt_still_verifies_after_the_key_is_rotated() -> None:
    old_account = Account.create()
    old_receipt = await mint(old_account, chain_id=84532)

    # The deployment rotates: a new key, and a different domain chain id.
    new_receipt = await mint(Account.create(), chain_id=1)

    assert verifies(old_receipt)
    assert verifies(new_receipt)
    assert old_receipt.signature.signer != new_receipt.signature.signer
    assert old_receipt.signature.chain_id == 84532
