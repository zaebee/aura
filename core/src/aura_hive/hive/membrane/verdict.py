from dataclasses import dataclass, field
from typing import Any, cast

from aura_core_gen.aura.core.v1 import (
    DecisionDerivation,
    DecisionOutcome,
)

# betterproto enums subclass int, so mypy reads a bare member access as `int`
# (the same reason ActionType is cast at every use below). Casting once here
# beats repeating it at each call site.
_EMIT = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_EMIT)
_OVERRIDE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_OVERRIDE)
_REFUSE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_REFUSE)
_UNAVAILABLE = cast(DecisionOutcome, DecisionOutcome.DECISION_OUTCOME_UNAVAILABLE)


@dataclass
class _Verdict:
    """
    The Membrane's finding, accumulated as the outbound path proceeds.

    Kept here rather than written onto the Intent as it goes, because the Intent
    on the override path is replaced part-way and a verdict half-written onto a
    discarded object is how `outcome_gate` nearly lost its first gate.

    **`gate` and `override_scope` answer different questions, so they
    accumulate by different rules.**

    `gate` answers "which rule explains this outcome". First gate wins *within
    an outcome class*, and resets when the class changes. Within a class the
    earlier gate is the one that explains the finding — a decision that trips
    DLP and then the floor check is reported as DLP_BLOCK — and holding to the
    first also keeps the schema stable and leaves the full detail to
    `gate_sequence`, which the auditor has. But first-wins *forever* was a bug:
    DLP → substitution → post-condition failure shipped
    `outcome=UNAVAILABLE, outcome_gate=DLP_BLOCK`, a receipt saying "unavailable
    because DLP" to the one party this document is written for, and one the
    error table contradicts (a psi failure is POSTCONDITION_VIOLATION) while
    `verify()` checks no gate/outcome coherence for UNAVAILABLE and so ships it
    silently. The gate that explained the previous class cannot explain the new
    one, so it is discarded with it.

    An earlier version of this docstring justified first-wins as denying an
    adversary an oracle over the policy configuration. That reasoning is a
    fossil: since the gateway trim the counterparty never sees `outcome_gate`
    at all. Schema stability and `gate_sequence` are the reasons that survive.

    `override_scope` answers "did the decidable content change", so it is
    **monotonic toward "value"** and does not ride `gate` at all. It starts
    empty, a prose-only intervention raises it to "prose", and a price
    substitution sets "value" unconditionally. Pairing it with the winning gate
    was the previous fix and it produced the branch's central contradiction: a
    DLP block followed by a price substitution reported `scope="prose"` while
    the digests differed, and `verify()` — which checks scope against the
    emission delta — failed a receipt the Membrane had just minted. Every
    intervention has to reach this field, because the question it answers is
    about all of them together, not about whichever one is named.

    It stays a property recomputed from `self.outcome` rather than a stored
    value some call site is trusted to clear, so a decision that moves past
    OVERRIDE can never leave a scope behind — there is no field to forget.
    """

    outcome: DecisionOutcome = _EMIT
    gate: str = ""
    ruleset_version: str = ""
    derivation: DecisionDerivation | None = None
    _scope: str = field(default="", repr=False)

    def record(self, outcome: DecisionOutcome, gate: str, scope: str = "") -> None:
        # Checked on EVERY OVERRIDE call, not only the one that establishes the
        # gate. Now that scope is monotonic, the second OVERRIDE record is
        # load-bearing on its own: it is what raises a DLP-then-substitution
        # decision from "prose" to "value". A call site that forgot its scope
        # there used to slip through this guard entirely and ship the receipt
        # `verify()` rejects.
        if outcome == _OVERRIDE and not scope:
            raise ValueError(
                f"gate {gate!r} recorded outcome OVERRIDE with no scope; "
                "every OVERRIDE call site must pass 'prose' or 'value'"
            )

        if outcome != self.outcome:
            # The class changed, so the gate that explained the old outcome is
            # not an explanation of this one. Replace it rather than keep it.
            self.gate = gate
        elif not self.gate:
            self.gate = gate

        self.outcome = outcome

        # Monotonic: value is absorbing, prose only fills an empty scope. Order
        # of interventions must not change the answer to "did the decidable
        # content change".
        if scope == "value":
            self._scope = "value"
        elif scope == "prose" and self._scope != "value":
            self._scope = "prose"

    @property
    def override_scope(self) -> str:
        """
        Whether this decision's interventions reached the decidable content,
        or "" when the final outcome is not OVERRIDE.

        Derived from `self.outcome` on every read instead of stored plainly,
        so it cannot outlive the OVERRIDE outcome that justified it — see the
        class docstring for the failure this closes.
        """
        return self._scope if self.outcome == _OVERRIDE else ""

    def read_guard_report(self, obs_meta: dict[str, Any]) -> None:
        """
        Take the rule set and the derivation from what the guard reported.

        `or ""` rather than a default, because `str(None)` is "None" — truthy,
        and it would record a sequence of that literal text and a hash claiming
        a derivation that never ran. A Struct round-trips a null value back as
        None, so a key being present is not the same as it carrying one.
        """
        self.ruleset_version = str(obs_meta.get("ruleset_version") or "")
        sequence = str(obs_meta.get("gate_sequence") or "")
        digest = str(obs_meta.get("derivation_hash") or "")
        # Left unset when no declared gate ran — a decision outside the guard's
        # scope, an unwired Membrane, or one of the Membrane's own checks, none
        # of which are declared in a rule set. Recording an empty digest there
        # would assert a derivation that never happened.
        if sequence or digest:
            self.derivation = DecisionDerivation(
                gate_sequence=sequence, derivation_hash=digest
            )
