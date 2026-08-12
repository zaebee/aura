"""
What an auditor gets when a counterparty cites a token.

Not just the document: the document plus whether it holds up. In a dispute the
second question is the one being asked.

The receipt here is minted by a real Membrane rather than written by hand. A
hand-built one cannot pass `verify()` — `canonical_prefix` is a digest of the
content fields, so inventing it makes the document fail for a reason that has
nothing to do with what is under test, and the exit code would be asserting
the fixture's invalidity rather than the tool's behaviour.
"""

import sys
from pathlib import Path

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
from aura_hive.hive.membrane.main import HiveMembrane
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from resolve_dispute import render  # noqa: E402


class _Safety:
    min_profit_margin = 0.10
    ui_trigger_price = 100000.0
    trade_risk_threshold = 0.10


async def a_minted_receipt() -> dict:
    """A receipt as the archive stores it: whatever `to_dict()` produced."""
    registry = SkillRegistry()
    guard = GuardSkill()
    guard.bind(_Safety(), OutputGuard(safety_settings=_Safety()))
    registry.register(guard.get_name(), guard)

    decision = await HiveMembrane(registry=registry).inspect_outbound(
        Intent(
            action=ActionType.ACTION_TYPE_COUNTER,
            reasoning="LLM reasoning",
            negotiation=NegotiationIntent(price=2000.0, message="Here is my offer"),
        ),
        Context(
            metadata=make_struct({"floor_price": "1000.0", "internal_cost": "777.0"}),
            hive=HiveContextData(request_id="req-2222"),
        ),
    )
    return dict(decision.receipt.to_dict())


@pytest.mark.asyncio
async def test_a_found_receipt_is_reported_with_its_verdict() -> None:
    receipt = await a_minted_receipt()

    report, code = render(receipt)

    assert receipt["decisionId"] in report
    assert "req-2222" in report
    assert "verify         ok" in report
    assert code == 0


@pytest.mark.asyncio
async def test_an_unsigned_receipt_is_named_as_unattested() -> None:
    """
    The auditor must not read "verified" as "vouched for". §7 keeps the two
    version names apart precisely so this distinction survives, and this
    Membrane has no attestation protein wired.
    """
    report, _ = render(await a_minted_receipt())

    assert "not attested" in report.lower()


@pytest.mark.asyncio
async def test_a_tampered_receipt_is_reported_as_failing() -> None:
    """
    The verdict is the point of the tool. A document that no longer matches
    its own digests must be named as failing, and the exit code must carry it
    so the command can gate something.
    """
    receipt = await a_minted_receipt()
    receipt["canonicalPrefix"] = "0" * 16

    report, code = render(receipt)

    assert "FAILED" in report
    assert code == 1


def test_a_missing_receipt_is_an_answer_not_a_failure() -> None:
    """
    A token that was never issued is a legitimate thing to tell an auditor.
    Exit 0, because the tool answered.
    """
    report, code = render(None)

    assert "not found" in report.lower()
    assert code == 0
