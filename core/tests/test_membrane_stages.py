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
