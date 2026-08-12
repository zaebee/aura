"""
The wire contract V2 depends on.

A separate file from test_receipt.py because this asserts the shape of the
generated types rather than any behaviour over them, and it is the first thing
to look at when a regeneration goes wrong.
"""

from aura_core_gen.aura.core.v1 import DecisionOutcome, DecisionReceipt


def test_unavailable_is_a_distinct_outcome() -> None:
    """
    A verdict nobody could establish is not a verdict against the decision.
    Sharing a value with REFUSE would make the two indistinguishable to a reader.
    """
    assert DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE == 4
    assert (
        DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE
        != DecisionOutcome.DECISION_OUTCOME_REFUSE
    )


def test_receipt_carries_the_binding_fields() -> None:
    """
    Without these a receipt describes an equivalence class of decisions rather
    than one decision: two negotiations for the same item at the same price
    produced a byte-identical receipt, signature included.
    """
    receipt = DecisionReceipt()
    assert receipt.issued_at == ""
    assert receipt.decision_id == ""
    assert receipt.request_id == ""
    assert receipt.override_scope == ""
