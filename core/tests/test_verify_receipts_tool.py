"""
The receipt's reader.

Until now `verify` existed only in tests: no receipts were persisted, so the
function that checks them had nothing to run against. The log line is the store
— it already fires on every decision — and this is what reads it.
"""

import json

from aura_core_gen.aura.core.v1 import (
    ActionType,
    DecisionOutcome,
    DecisionReceipt,
    Intent,
    NegotiationIntent,
)
from aura_hive.hive.membrane.receipt import mint

from tools.verify_receipts import read_receipts, summarise


def line(**receipt_fields: object) -> str:
    return json.dumps({"event": "membrane_receipt", "receipt": receipt_fields})


def counter(price: float, item: str = "htl-9931", message: str = "an offer") -> Intent:
    return Intent(
        action=ActionType.ACTION_TYPE_COUNTER,
        reasoning="the model's private reasoning",
        negotiation=NegotiationIntent(
            item_identifier=item, price=price, message=message, thought="a thought"
        ),
    )


def an_ok_receipt() -> DecisionReceipt:
    """A minted receipt, untouched — its prefix matches its content fields."""
    return mint(counter(100.0), counter(100.0), DecisionOutcome.DECISION_OUTCOME_EMIT)


def a_tampered_receipt() -> DecisionReceipt:
    """One whose content moved after minting, so the prefix no longer commits to it."""
    receipt = an_ok_receipt()
    receipt.outcome_gate = "INVENTED_AFTER_THE_FACT"
    return receipt


class TestReading:
    def test_it_ignores_lines_that_are_not_receipts(self) -> None:
        lines = [
            json.dumps({"event": "heartbeat"}),
            line(version="AURA-RECEIPT-V2-UNSIGNED"),
        ]
        assert len(list(read_receipts(lines))) == 1

    def test_it_survives_a_line_that_is_not_json(self) -> None:
        """
        A log is a stream someone else writes. A truncated line at the end of a
        rotated file must not stop the audit of everything before it.
        """
        assert (
            len(
                list(
                    read_receipts(
                        ["{not json", line(version="AURA-RECEIPT-V2-UNSIGNED")]
                    )
                )
            )
            == 1
        )


class TestSummarising:
    def test_it_counts_what_verified_and_what_did_not(self) -> None:
        summary = summarise([an_ok_receipt(), a_tampered_receipt()])
        assert summary.checked == 2
        assert summary.ok == 1
        assert len(summary.failures) == 1

    def test_it_tallies_what_could_not_be_checked(self) -> None:
        summary = summarise([an_ok_receipt()])
        assert summary.unverifiable["emission_content"] == 1
