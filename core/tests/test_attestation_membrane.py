"""
The Membrane asks the attestation protein, not the payments protein.

Nothing in production was signed, because signing lived behind
`crypto.enabled`. This asserts the new address of the key AND the promise that
survives it: a signing failure never costs the decision.
"""

from typing import Any

import pytest
from aura_core import SkillRegistry
from aura_core.struct_utils import make_struct
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
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
    """
    What the Membrane reads off `self.settings`.

    `safety` is carried even though these tests never reach it:
    `inspect_outbound` reads `self.settings.safety.trade_risk_threshold` on the
    trade path, and a stub missing it fails only for whoever adds the first
    trade test here.
    """

    def __init__(self, chain_id: int = 84532) -> None:
        self.attestation = AttestationSettings(chain_id=chain_id)
        self.safety = SafetySettings()


def membrane_with(attestation: Any | None) -> HiveMembrane:
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)
    if attestation is not None:
        registry.register("attestation", attestation)
    membrane = HiveMembrane(registry=registry)
    membrane.settings = _Settings()
    return membrane


def context() -> Context:
    return Context(
        metadata=make_struct({"floor_price": "1000.0", "internal_cost": "777.0"}),
        hive=HiveContextData(request_id="req-attest"),
    )


def counter(price: float) -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=price, message="Here is my offer"),
    )


def bound_skill(account: Any) -> AttestationSkill:
    skill = AttestationSkill()
    skill.bind(AttestationSettings(), AttestationEngine(account.key.hex()))
    return skill


class TestTheMembraneAttests:
    @pytest.mark.asyncio
    async def test_a_signed_receipt_recovers_to_the_configured_signer(self) -> None:
        account = Account.create()

        decision = await membrane_with(bound_skill(account)).inspect_outbound(
            counter(price=2000.0), context()
        )

        receipt = decision.receipt
        assert receipt.version == "AURA-RECEIPT-V2"
        assert receipt.signature.signer == account.address

        # Every domain field from the receipt, as `_check_signature` does.
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
        assert recovered == account.address

    @pytest.mark.asyncio
    async def test_no_attestation_protein_leaves_the_receipt_unsigned(self) -> None:
        decision = await membrane_with(None).inspect_outbound(
            counter(price=2000.0), context()
        )

        assert decision.receipt.version == "AURA-RECEIPT-V2-UNSIGNED"
        assert decision.negotiation.price == 2000.0

    @pytest.mark.asyncio
    async def test_a_signing_failure_does_not_cost_the_decision(self) -> None:
        class _Broken(AttestationSkill):
            async def execute(self, intent: str, params: dict[str, Any]) -> Any:
                raise RuntimeError("key unreachable")

        decision = await membrane_with(_Broken()).inspect_outbound(
            counter(price=2000.0), context()
        )

        assert decision.receipt.version == "AURA-RECEIPT-V2-UNSIGNED"
        assert decision.action == ActionType.ACTION_TYPE_COUNTER
        assert decision.negotiation.price == 2000.0
