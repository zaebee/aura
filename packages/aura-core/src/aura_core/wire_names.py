"""
Canonical names for protobuf enums that appear in signed content.

`DecisionOutcome` is one of the fields an AURA-RECEIPT-V1 signature covers, and
it is signed by name rather than by its protobuf integer — so that what travels
on the wire and what was signed are the same string, with no mapping step in the
middle of a consumer's signature reconstruction for them to get wrong.

Which means the mapping must have exactly one implementation. It lives in the
Genome because both sides need it and neither may own it: the Membrane produces
the signed content, the api-gateway renders the same value into JSON, and a
second implementation drifting from the first would silently invalidate every
signature it touched.

Pure: standard library only, no project imports.
"""

from typing import Any

_DECISION_OUTCOME_PREFIX = "DECISION_OUTCOME_"

_DECISION_OUTCOMES = {
    0: "unspecified",
    1: "emit",
    2: "override",
    3: "refuse",
}


def decision_outcome_name(outcome: Any) -> str:
    """
    `override`, not `2`.

    Falls back to a rendering of whatever it was handed rather than raising:
    this is used to build a log line and a JSON field, and neither is worth
    failing a decision over. An unknown number renders distinctly so it cannot
    be mistaken for a known outcome.
    """
    try:
        key = int(outcome)
    except (TypeError, ValueError):
        return f"outcome_{outcome}"

    return _DECISION_OUTCOMES.get(key, f"outcome_{key}")
