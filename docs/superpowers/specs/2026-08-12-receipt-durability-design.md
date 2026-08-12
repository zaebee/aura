# Receipt durability and dispute lookup — design

**Status:** approved, not implemented
**Date:** 2026-08-12
**Follows:** `2026-08-12-attestation-protein-design.md`, `2026-08-11-decision-receipt-v2-design.md`

## Why

**The corpus does not survive.**

`docs/DECISION_RECEIPT.md` §7 says "the log line makes the log the store". It does — for days to
weeks. `membrane_receipt` goes to Loki, which lives in the `monitoring` namespace outside this
repository and retains for a short window. Nothing writes a receipt anywhere else:
`grep -rn "receipt" core/src/aura_hive/hive/proteins/persistence/` finds nothing.

So a dispute arriving a month after the decision finds nothing to resolve, and the branch that
taught the Hive to sign its receipts bought a corpus that evaporates before a consumer can read it.

This is the same time-shape that justified the attestation work and it applies harder here. A
receipt minted unsigned is permanently unattestable; a receipt that expires is permanently gone.
Neither can be repaired later. A lookup API, by contrast, can be built at any time over data that
still exists — which is why **durability is the work and the resolver falls out of it**, rather than
the other way round.

## What this is not

There is no dispute process yet, and no counterparty has ever cited a token. This design does not
build a public endpoint, an authorisation model, a dispute workflow, or a retention policy. It makes
receipts stop disappearing, and gives the auditor one command.

The lookup deliberately lives in the persistence protein rather than in the tool, so that an internal
endpoint later is a second thin caller rather than a rewrite. That is the only concession to a future
that may not arrive, and it costs nothing today.

## Decisions

**The Connector writes, on the C step.** Considered and rejected: (a) the Membrane writing where it
mints — it is the single funnel every receipt passes through, which is attractive, but it puts a
Postgres round-trip inside a boundary check on the decision path; the Membrane performs exactly one
synchronous call today, to the guard, and paying negotiation latency for an archive is the wrong
trade; (b) a separate consumer tailing the log — full decoupling and nothing added to the hot path,
but it adds a deployable moving part and, fatally, builds the archive on top of the very
short-retention stream this design exists to escape.

The Connector is the "act" step, already holds the persistence protein, and already copies
`dispute_token` onto the observation. `MetabolicLoop` calls `connector.act` unconditionally after
the outbound Membrane (`metabolism/main.py:74`), so **refused decisions reach it too** — which
matters, because "you refused me" is exactly the dispute a counterparty brings.

**The write is fail-open.** A failure logs and is swallowed; the decision proceeds. This is the rule
the receipt log line already follows and states: reporting on a decision must never take that
decision down.

**The log line stays.** Two independent paths, not a replacement. The log survives Postgres being
unreachable and costs nothing extra.

**No retention policy, no cleanup job.** A receipt is digests and identifiers — on the order of a
kilobyte — so a million decisions is about a gigabyte. Deleting the archive on a timer is precisely
the disease being cured. The growth is unbounded and this document says so on purpose; revisit when
the table is large enough to measure, not before.

## Architecture

```
MetabolicLoop
  └─ connector.act(decision, context)          ← already called for every decision
       └─ registry.execute("persistence", "record_receipt", {...})   [fail-open]
            └─ ReceiptRepository.record(...)

tools/resolve_dispute.py   (make resolve-dispute TOKEN=…)
  └─ registry.execute("persistence", "find_receipt_by_dispute_token", {...})
       └─ ReceiptRepository.find_by_dispute_token(...)
            └─ verify() over what came back
```

### Storage

A `DecisionReceiptRecord` model in `persistence/engine.py`, beside `InventoryItem` and `LockedDeal`,
following the same `DeclarativeBase` / `Mapped[...]` pattern.

| column | type | note |
|---|---|---|
| `dispute_token` | `String`, unique index | what the counterparty cites; the lookup key |
| `decision_id` | `String`, index | what the signature binds; the auditor's other way in |
| `request_id` | `String`, index | the session, for reassembling a negotiation |
| `issued_at` | `String` | the receipt's own timestamp, not the write's — stored as the string the receipt carries rather than parsed into a `DateTime`, so the column holds what was signed rather than a reconstruction of it |
| `receipt` | `JSONB` | the whole document, exactly as logged |
| `recorded_at` | `DateTime` | when the row was written |

**The receipt is stored whole rather than decomposed.** `verify()` takes a document, and every
normalisation is an opportunity to reassemble something at read time that differs from what was
signed. The indexed columns are duplicated out of the JSON for lookup only; the JSON is the record.

**Nothing here leaks.** §7 already establishes it: no field of `DecisionReceipt`,
`DecisionDerivation` or `ReceiptSignature` is a price or a premise value — every one is a digest, an
identifier, an enum, a timestamp, or signature metadata. The table does not become a new place where
`floor_price` lives.

### Components

**`ReceiptRepository`** (`persistence/receipts.py`) — one file beside `deals.py`, `items.py`,
`wallet.py`. Two methods: `record(receipt_dict, dispute_token)` and
`find_by_dispute_token(token) -> dict | None`.

**Two new persistence capabilities** (`persistence/skill.py`), added to the `_capabilities` map
alongside the existing ones:

- `record_receipt` takes `{"receipt": dict, "dispute_token": str}` — the receipt as
  `decision.receipt.to_dict()`, which is the same rendering the log line carries. The skill derives
  `decision_id`, `request_id` and `issued_at` from the receipt dict rather than accepting them
  separately, so the indexed columns cannot disagree with the document they index. Returns
  `Observation(success=True)`, or a failed Observation carrying the error.
- `find_receipt_by_dispute_token` takes `{"dispute_token": str}` and returns
  `Observation(success=True, metadata={"receipt": …})` when found, or `Observation(success=False,
  error="not_found")`. Absence is a normal answer, so it is not an exception.

**`tools/resolve_dispute.py`**, wired as `make resolve-dispute TOKEN=…` beside `verify-receipts`.
Finds, runs `verify()`, prints the receipt and the verdict.

## Error handling

**Recording:** any exception is caught at the Connector, logged as `receipt_record_failed` with the
`dispute_token`, and the decision proceeds untouched.

The gap this leaves is worth stating rather than discovering: **fail-open means archive holes are
possible and silent.** `receipt_record_failed` is a distinct event precisely so it can carry an
alert — otherwise this design replaces "the data disappears after a week" with "the data sometimes
never arrives", which is worse because nothing announces it. The log line remains as the second path,
so a failed write is not automatically a lost receipt.

**Resolving:** an unknown token prints "not found" and exits **0**. A token that was never issued is
a legitimate answer to give an auditor — someone may have invented it — not a tool failure. A
database that cannot be reached exits non-zero, because that is the tool failing rather than
answering.

## Testing

- **A recorded receipt is found by its token**, driven through the protein against a real session,
  as the existing repository tests do.
- **A refused decision is recorded too.** This is the case the Connector-writes decision was checked
  against; a dispute about a refusal is the likeliest dispute there is.
- **A database failure does not cost the decision:** the observation still returns, and
  `receipt_record_failed` is logged.
- **A receipt still verifies after the round trip through Postgres.** The single most important test
  here: JSON serialisation must not disturb a signed document. If this fails the archive is
  decorative.
- **An unknown token reports not-found and exits 0.**
- **Two decisions in one session** both resolve, and share a `request_id` — the field exists for
  reassembly and nothing else asserts it.

## Risks

**Silent archive holes**, as above. Mitigated by a distinct failure event and by the log line
remaining; not eliminated.

**Unbounded growth**, accepted deliberately and documented rather than solved.

**Write amplification on the decision path.** One insert per decision, on a path that already does a
guard round-trip and a log write. If it ever shows up in latency, the answer is to move the write off
the request path (a queue, or the log-tailing consumer rejected above) rather than to drop it.

## Out of scope

The internal or public endpoint, its authorisation model, and any revisit of §1.1's decision that
the reader is an auditor. The §3.4 residual (`proposed_price` in the response, the jitter bound
decaying with N). Backfilling receipts that have already expired — they are gone, which is the point.
