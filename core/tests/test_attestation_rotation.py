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
from aura_hive.hive.membrane.receipt import signing_payload
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
    """Recovery only — no private key is involved, which is the whole point."""
    payload = signing_payload(receipt, chain_id=receipt.signature.chain_id)
    raw = bytes.fromhex(receipt.signature.signature.removeprefix("0x"))
    recovered = Account.recover_message(
        encode_typed_data(full_message=payload), signature=raw
    )
    return bool(recovered == receipt.signature.signer)


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
