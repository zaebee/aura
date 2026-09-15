"""Outbound stages in isolation: what the 400-line method hid."""

import pytest
from aura_hive.hive.membrane.outbound import Attestation, Postcondition


@pytest.mark.asyncio
async def test_unsigned_receipt_passes_through_when_no_key():
    """Attestation without a wired key returns the receipt unsigned —
    the decision stands, only the proof is absent."""
    from aura_core_gen.aura.core.v1 import DecisionReceipt

    attestation = Attestation(registry=None)
    receipt = DecisionReceipt()
    assert await attestation.sign(receipt) == receipt


@pytest.mark.asyncio
async def test_postcondition_without_guard_is_unreachable_not_a_pass():
    """No registry means no verdict could be established — False, not True."""
    from aura_hive.hive.membrane.verdict import _UNAVAILABLE, _Verdict

    postcondition = Postcondition(registry=None)
    verdict = _Verdict()
    assert await postcondition.verify(100.0, {}, verdict) is False
    assert verdict.outcome == _UNAVAILABLE
    assert verdict.gate == "POSTCONDITION_VIOLATION"


@pytest.mark.asyncio
async def test_null_safe_price_in_recovery_falls_back_to_floor_markup():
    """A guard Observation carrying safe_price=null (Struct null
    round-trips as None) must not raise float(str(None)). The substitute
    prices from the floor markup and goes through psi openly: here cost
    defaults to the floor, so 1050 at m=0.1 cannot satisfy the margin and
    the receipt says POSTCONDITION_VIOLATION instead of crashing."""
    from unittest.mock import AsyncMock, MagicMock

    from aura_core.struct_utils import make_struct
    from aura_core_gen.aura.core.v1 import (
        ActionType,
        Context,
        Intent,
        Observation,
    )
    from aura_hive.hive.membrane.main import HiveMembrane

    null_meta = make_struct({"safe_price": None})

    async def _execute(skill: str, intent: str, params: dict):
        return Observation(success=True, metadata=null_meta)

    registry = MagicMock()
    registry.execute = AsyncMock(side_effect=_execute)
    membrane = HiveMembrane(registry=registry)

    decision = await membrane.inspect_outbound(
        Intent(action=ActionType.ACTION_TYPE_ERROR, reasoning="LLM blew up"),
        Context(metadata=make_struct({"floor_price": "1000.0"})),
    )

    assert decision.receipt.outcome_gate == "POSTCONDITION_VIOLATION"
