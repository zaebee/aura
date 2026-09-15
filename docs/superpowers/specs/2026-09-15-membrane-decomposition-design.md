# Membrane Decomposition — Design

Date: 2026-09-15. Approach: thin package (A).

## Problem

`core/src/aura_hive/hive/membrane/main.py` (1174 lines, top churn: 24
commits since June) is a God object: the `_Verdict` record type, Intent
shaping helpers, Prometheus metrics, and the `HiveMembrane` cell with a
400-line `inspect_outbound` all share one file. Only two modules import
it (`cortex.py`, `hive/__init__.py`), both through `HiveMembrane`.

## Layout

New structure of `core/src/aura_hive/hive/membrane/`:

- `verdict.py` — `_Verdict` verbatim (derivation record, `override_scope`,
  guard-report reading).
- `shaping.py` — Intent constructors (`_replacing`, `_rejection`,
  price/text helpers, `_mint_for`, `_as_dict`, `_context_number`).
- `metrics.py` — intervention counters.
- `inbound.py` — `InboundScreening` (current `inspect_inbound` body).
- `outbound.py` — `Attestation`, `Postcondition`, `Substitution` stages
  plus a thin `OutboundPipeline` running them in order.
- `main.py` — `HiveMembrane` only: builds collaborators in `__init__`,
  `inspect_inbound`/`inspect_outbound` delegate. Under 250 lines.

`receipt.py` untouched.

## Interfaces and data flow

Each collaborator is constructed in `HiveMembrane.__init__` from the
already-available registry and settings:

- `InboundScreening.check(signal) -> signal`
- `Attestation.sign(receipt) -> receipt`
- `Postcondition.verify(price, guard_context, verdict) -> holds`
- `Substitution.offer(original, safe_price, reason, verdict, guard_context, request_id, claim=None) -> Intent`
- `Substitution.finish(claim, emission, verdict, request_id) -> Intent`
- `OutboundPipeline.run(decision, context, verdict)` — attest, then
  postcondition, then substitute-on-violation, recording into the
  passed-in `_Verdict`.

Boundary rules: collaborators know nothing of each other (only the
pipeline calls them); no direct registry access except guard calls
through the passed registry; shared mutable state is the `_Verdict`
passed by reference. Public surface (`inspect_inbound`,
`inspect_outbound`, Trinity `bind`/`initialize`/`execute`) is
byte-identical. No new error types: violations stay on the
`SafetyViolation` path, unavailability on the `GuardUnavailable` path.

## Tests and migration

Existing membrane tests pin the public contract and must pass
unmodified — that is the done-criterion for "contract intact". New
tests cover the previously untestable interiors (unsigned attest,
postcondition failure, substitute volume) via direct collaborator
construction with a mocked registry.

Three shippable increments:

1. Pure modules (`verdict.py`, `shaping.py`, `metrics.py`), moved 1:1,
   with `main.py` re-exporting names so even direct importers survive.
2. `InboundScreening` plus outbound stages as classes; `HiveMembrane`
   delegates.
3. Cleanup: drop transitional re-exports, full suite + ruff.

Done when: `main.py` under 250 lines, all pre-existing tests green
without edits, stages covered by new tests.
