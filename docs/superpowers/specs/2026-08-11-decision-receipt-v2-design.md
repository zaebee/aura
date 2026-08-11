# Decision receipt V2 — design

**Status:** design, approved, revised after audit, not implemented (2026-08-11)
**Branch:** `feat/decision-receipt-v2`
**Base:** `origin/main` @ 4d1d70d

## Why

A literature review of `docs/DECISION_RECEIPT.md` against the certifying-algorithms
and remote-attestation traditions found that the receipt is a well-built artefact
of the wrong class, and — while writing the missing post-condition down — turned up
a live bug in the guard.

**The bug.** With `floor = 100`, `min_profit_margin = 0.1` and `internal_cost`
unset:

- `membrane/main.py` defaults `internal_cost` to `floor_price`, so cost = 100;
- the model proposes 92, `G2_FLOOR_VIOLATION` fails, and `OutputGuard.evaluate`
  returns immediately — **`G4_MARGIN_VIOLATION` never runs**;
- the override substitutes `floor × 1.05 = 105` and emits it;
- realised margin is `(105 − 100) / 105 = 0.0476`, against a configured minimum
  of `0.1`.

The system emits a price violating its own minimum-margin rule, on the default
configuration, and the receipt for that decision is entirely valid: `G2:fail` is
truthfully recorded, the hashes reconcile, the signature verifies. Gates judge
**what the model proposed**; nothing judges **what the Membrane substituted**.
That gap opened the moment `override` was introduced as a third outcome and has
been open since.

**The class error.** McConnell, Mehlhorn, Näher & Schweitzer (*Certifying
Algorithms*, Computer Science Review 5(2), 2011) define a witness predicate as
requiring two properties: checkability *and* simplicity — the latter meaning
`W(x,y,w) → ψ(x,y)` has an elementary proof. §5.5 then rules out two degenerate
certificates by name. The first is, verbatim, taking `w` as "the record of the
computation of P on x", which "does not satisfy the simplicity requirement, since
a proof of the witness property is tantamount to proving the correctness of P."

Our `gate_sequence` + `derivation_hash` is that example. Two consequences:

1. **ψ was never written down.** `ruleset_version` names a rule set, but nowhere
   in the repo or the doc does anything state what that rule set *guarantees*.
   That is the difference between a certificate and a version string — and it is
   why the bug above went unnoticed.
2. **`verify()` is not a checker.** A checker is `C(x, y, w)`; §6.2 is explicit
   that it must read the original, unmanipulated input. Ours receives only the
   receipt. It cannot learn that `claim_hash` is the digest of anything real.

We are not fixing (2) here — closing it needs `premise_hash`, which stays
deferred for the reasons already recorded in `DECISION_RECEIPT.md` §3.1. We are
making `verify()` **say** it, and fixing everything reachable without it.

**Audience.** Decided during design: the receipt is addressed to an **auditor**,
not to the counterparty we negotiate against. Everything below follows from that
one choice.

## Scope

**In:** collapse the two safe-price strategies into one that satisfies the margin
rule; declare ψ in `ruleset.yaml` and check it on the emitted value; format
`AURA-RECEIPT-V2` with transaction binding and freshness; delete V0/V1; trim the
gateway's client-facing view; put the full receipt in the structured log and add a
verification utility; correct `DECISION_RECEIPT.md`.

**Out:** `premise_hash` and `policy_stamp` (§3.1, §3.5 — still waiting on "who
opens it, and when"); a witness for the `refuse` path (needs a second rule-set
family, its own spec); receipt storage through `PersistenceSkill`; content-
addressing of predicate bodies (§3.3 caveat stands); the counterparty-verifiable
variant of the receipt, which the audience decision rules out.

## Audit note

The first draft of this spec was audited against the source by an independent
reviewer briefed to refute rather than review. It confirmed the bug in *Why*
end-to-end and all five supporting claims, and **broke two of the three
load-bearing decisions**:

1. **The collapsed safe price failed ψ at the default configuration.**
   `round(floor/(1−m), 2)` rounds down; at `floor = 100, m = 0.1` that is `111.11`
   for a required `111.1111…`, and a lower price is a lower margin. Since a ψ
   failure is fail-closed, the "fix" would have refused the guard's own safe offer.
   Independent re-checking widened this: over a random `(floor, cost, m)` grid the
   original formula violated ψ in **115 888 of 200 000** cases, not just at the
   default; and after correcting the rounding, ~4 000 violations remained where the
   price was *exactly* right and only the binary-float ratio disagreed. That second
   layer was not in the audit and is the more dangerous of the two. Decisions 2, 2a,
   2b and 5a are the response.

2. **Trimming the client's receipt view did not close the floor inversion.** The
   substitute price reaches the client as `proposed_price` regardless, and the
   override announces itself in plain English. Decisions 10, 10a–10c are the
   response, and 10c states plainly that the result is a bounded disclosure rather
   than a closed one.

It also found ψ's stated coverage overclaimed (Decision 5, now narrowed) and
confirmed Decision 8 — no persisted receipts exist anywhere, so there is nothing to
migrate.

## Decisions

| # | decision | why |
|---|---|---|
| 1 | Receipt is for the **auditor**, not the counterparty | The design pays the full cost of counterparty verification (EIP-712, self-describing domain, key-free `verify`, ERC-8004 resolution) and cannot deliver it: the verifier has no input, no freshness and no transparency log. Choosing the reachable audience makes every other decision below consistent. |
| 2 | **One** safe-price strategy, not two | Once the substitute is `max(floor × 1.05, max(floor, internal_cost) / (1 − m))` it is **always ≥** the old `margin` strategy, so the two no longer differ in guarantee. Two strategies with indistinguishable guarantees is the crack the bug came through. *(Revised after audit — see Audit note. The first version of this decision used `floor / (1 − m)`, ignored `internal_cost`, and reasoned in exact reals.)* |
| 2a | The substitute rounds **up**, in `Decimal` | `round(…, 2)` rounds toward the nearest cent, which for a margin substitute means half the time toward breaching it: at `floor = 100, m = 0.1` it emits `111.11` for a required `111.1111…`, and `d/dp[(p−c)/p] > 0` makes the lower price the lower margin. A value that exists to be safe must round in the direction of the guarantee, never away from it. `ROUND_CEILING` on `Decimal`, not `round()` on `float`. |
| 2b | The substitute depends on `internal_cost`, not just `floor` | ψ's margin clause is checked against `internal_cost`, which `membrane/main.py` merely *defaults* to `floor_price` and which arrives independently. Where `internal_cost > floor`, no price derived from `floor` alone can satisfy ψ, and the guard would refuse its own safe offer. |
| 3 | Collapsing also **moves the ruleset digest** | The digest covers the declared structure, not the predicate bodies (`DECISION_RECEIPT.md` §3.3 states this as a known limit). Changing `floor_markup`'s body while keeping its name would therefore change the guarantee without moving `ruleset_version` — the exact failure that limit describes. Removing the per-gate `safe_price` key changes the hashed structure, so the digest moves on its own; the semver bump to `2.0.0` is deliberate on top of that, not a substitute for it. |
| 4 | ψ declared **like gates**: id + prose `expr`, predicate matched by id | Reuses the pattern `Ruleset.validate_against` already implements and tests, in both directions. No expression evaluator enters the codebase; `expr` is text for the digest and for a human reader. |
| 5 | ψ is checked **on the emission**, in the Membrane, on **both** the `emit` and `override` paths of the negotiation flow | The value that leaves only exists at the outbound boundary. Checking only the override path would miss a broken gate on the `emit` path; checking only `emit` would have missed this bug. Scope is the negotiation flow specifically: `trade` and `rwa_vault` return before the guard block and are judged by no rule set, so `guard/negotiation`'s ψ does not and must not claim to cover them — they need sibling families, which §3.3 already says and which stays out of scope. |
| 5a | ψ's margin clause is **multiplicative**, in `Decimal` | `(price − cost) / price >= m` in binary floats on money is not decidable: at prices where the value is exactly right, the ratio evaluates to `0.09999999999999995` against `0.1`. Because ψ is fail-closed, a 5e-17 artefact turns a correct decision into a hard refusal. `price × (1 − m) >= cost` is algebraically identical for `price > 0`, has no division, and is exact over `Decimal`. |
| 6 | ψ violation is a **new outcome**, not a gate failure | A gate firing means a rule judged the proposal. ψ failing means we are broken. AR4SI (`draft-ietf-rats-ar4si`) separates these: `-1` "verifier malfunction" is not a member of the tier that carries appraisal failures. `DECISION_OUTCOME_UNAVAILABLE` carries it, readable from `outcome` rather than by parsing `outcome_gate` strings. |
| 7 | Binding fields go in **content fields**, so the version must move | Binding that is not signed is decorative — anyone can rewrite it. Signing changes, so the format generation changes. There is no variant where these fields are added in place. |
| 8 | V0/V1 are **deleted, not deprecated** | No persisted receipts exist: the doc's step 6 records that the bee-keeper half was never built, and the log line carries five scalar fields rather than a document. There is no legacy corpus to migrate. |
| 9 | `unverifiable` gains **`emission_content`** on every receipt | The honest fix for "`verify()` is not a checker" is not a rename: it is the function telling its own caller that it never saw the Intent and cannot vouch that `claim_hash` digests anything real. A reader learns this from the result, not from someone else's documentation. |
| 10 | Client gets `version` + `canonical_prefix` **only** | Removing `outcome`, `outcome_gate` and the hashes from the HTTP response is right on its own terms — none of it means anything to a party that is not the audience. It is **not**, however, what closes the floor inversion; see 10a. *(Revised after audit: the first version of this decision claimed it was.)* |
| 10a | The substitute price carries **per-session jitter**, and the override message is neutralised | The inversion does not run through the receipt at all. `proposed_price` reaches the client on every counter, and the override emits a fixed `"I've reached my final limit… My best offer is $X."` (`membrane/main.py:655`) that reaches it verbatim through `connector/main.py:98` → `api-gateway/main.py:331`. A deterministic substitute plus a recognisable message is an exact disclosure no receipt trimming can undo. `j = ε · HMAC(secret, request_id) / 2²⁵⁶` with `ε = 0.03`, applied as `× (1 + j)` before the ceiling. Constant within a session, so repeated rounds cannot average it away; varying across sessions, so a corpus of deals cannot either. |
| 10b | The jitter secret is **process-lifetime random**, not configured | The auditor does not need to reproduce the price — ψ checks the value, which is the whole reason ψ is executable. So there is no reproducibility requirement to satisfy, and therefore no setting to add, no fail-closed branch for a missing secret, and nothing to rotate or leak. A restart mid-session reshuffles the jitter, which only adds noise for the counterparty. |
| 10c | The disclosure is **bounded, not closed**, and the doc says so | `ε` is a source constant and therefore public, so the counterparty learns `floor` to within `ε`. Neutralising the message reduces but does not remove distinguishability: a templated counter still reads differently from the model's own prose, and fully closing that needs the model to phrase the substituted price — its own piece of work. The only design that closes the channel outright is refusing instead of countering, which `DECISION_RECEIPT.md` §3.6 rejects on product grounds. That trade is now stated rather than assumed. |
| 11 | Freshness via **timestamp**, not nonce | RFC 9334 §10 offers synchronized clocks, nonces or epoch IDs. A nonce requires a challenge from the relying party, which the audience decision removes and which would change the `/v1/negotiate` contract and every synapse. |
| 12 | Consumer is the **structured log + a CLI**, not new storage | `logger.info("membrane_receipt", …)` already fires on every decision. Widening it to carry the document, plus a script that runs `verify()` over the stream, gives the receipt a reader on the day this merges, with no schema, no migration and no new responsibility on the already-overloaded `PersistenceSkill`. |

## Architecture

Nothing moves between components. The guard owns the rules and therefore owns ψ's
predicates; the Membrane owns the outbound boundary and therefore owns the *call*.

```
signal → M(in) → A → T → M(out) ────────────────────────────→ C → G
                          │
                          ├─ guard.validate_decision(proposal, ctx)   gates → derivation
                          ├─ [on failure] guard.safe_offer(ctx)       one strategy
                          ├─ guard.check_postcondition(emitted, ctx)  ψ, BOTH paths   ← new
                          └─ mint(claim, emission, verdict) → sign → Intent.receipt
```

`check_postcondition` runs after the emitted value is settled and before the
receipt is minted, so a ψ failure is recorded as the decision's outcome rather
than discovered after a receipt has already asserted something else.

## Rule set schema

`core/src/aura_hive/hive/proteins/guard/ruleset.yaml`, at `version: 2.0.0`:

```yaml
family: guard/negotiation
version: 2.0.0

# One strategy for the whole set (was per-gate). max() of the two former
# formulas, so every gate errs toward the seller by construction.
safe_price: safe_offer

postcondition:
  id: PSI_NEGOTIATION_V1
  clauses:
    - id: PSI_PRICE_POSITIVE
      expr: "price > 0"
      consumes: [price]
    - id: PSI_ABOVE_FLOOR
      expr: "price >= floor_price"
      consumes: [price, floor_price]
    # Multiplicative, not (price - cost)/price >= m. Decision 5a: the ratio form
    # is not decidable in binary floats on money, and psi is fail-closed.
    - id: PSI_MIN_MARGIN
      expr: "price * (1 - min_profit_margin) >= internal_cost"
      consumes: [price, internal_cost]

gates:
  - {id: G1_PRICE_POSITIVE,  code: INVALID_PRICE,          consumes: [price]}
  - {id: G2_FLOOR_VIOLATION, code: FLOOR_PRICE_VIOLATION,  consumes: [price, floor_price]}
  - {id: G3_SETTINGS_PRESENT, code: SETTINGS_MISSING,      consumes: []}
  - {id: G4_MARGIN_VIOLATION, code: MIN_MARGIN_VIOLATION,  consumes: [price, internal_cost]}
```

Gate order is unchanged and remains load-bearing: it decides which reason a
refusal carries.

```
safe_offer(context) =
    ceil_to_cents( max(floor × 1.05, max(floor, internal_cost) / (1 − m)) × (1 + j) )

    j = ε · HMAC_SHA256(process_secret, request_id) / 2²⁵⁶,   ε = 0.03
```

`Decimal` throughout with `ROUND_CEILING` — never `float`, never `round()`
(Decisions 2a, 5a). `m` comes from `_configured_margin()`, which already clamps to
`[0.0, 1.0)` and falls back to the default, so a missing or corrupt setting cannot
produce a price below the floor. `(1 + j) ≥ 1` and the ceiling rounds up, so
jitter cannot break ψ — verified over 200 000 random `(floor, internal_cost, m,
request_id)` combinations at zero violations, against 115 888 for the formula this
replaces.

`Ruleset.validate_against` grows a second cross-check over `postcondition.clauses`
against the implemented clause ids, in both directions, on the same reasoning as
gates: a declared clause with no predicate is never evaluated while the rule set
advertises it, and an undeclared predicate runs outside anything a receipt
accounts for.

## Receipt schema

`DecisionOutcome` gains one value:

```protobuf
DECISION_OUTCOME_UNAVAILABLE = 4;  // no verdict could be established
```

`DecisionReceipt` gains four fields (numbers 9–10 stay reserved for
`premise_hash` / `policy_stamp`):

| field | no. | source | purpose |
|---|---|---|---|
| `issued_at` | 12 | Membrane clock, RFC3339 UTC | freshness — RFC 9334 §10, synchronized-clock variant |
| `decision_id` | 13 | `Intent.identifier` of the emission | binds the receipt to one decision |
| `request_id` | 14 | `HiveContextData.request_id` | groups decisions into a session for the auditor |
| `override_scope` | 15 | Membrane | `"value"` \| `"prose"`; empty unless `outcome == OVERRIDE` |

`trace_id` is deliberately absent: the log line that carries the receipt carries
the trace context beside it.

**Content fields**, signed, in this order — order is part of canonicalisation:

```
version
issued_at
decision_id
request_id
claim_hash
ruleset_version
derivation.derivation_hash      (empty string when derivation is unset)
emission_hash
outcome                         (the name, e.g. "override")
outcome_gate
override_scope
```

**Version names:** `AURA-RECEIPT-V2` (signed) and `AURA-RECEIPT-V2-UNSIGNED`. The
number is the format generation; the suffix is attestation. The V0/V1 pair
encoded attestation in the generation number and is removed.

`canonical_claim` for `negotiation` gains `currency`, resolving the divergence
where the doc (§3.2, §4) promises `action;item;price;currency` and the code emits
`action;item;price`. The `trade` branch already carries it.

## Components

**`proteins/guard/ruleset.py`** — parse and validate the `postcondition` block;
drop the per-gate `safe_price` key and read the set-level one; extend
`validate_against` to clause ids. Digest covers the new structure.

**`proteins/guard/engine.py`** — replace `calculate_safe_price`'s strategy table
with the single `safe_offer` formula above, on `Decimal` with `ROUND_CEILING`, and
add the per-session jitter (module-level `secrets.token_bytes(32)` at import,
`ε = 0.03` as a named constant); add
`check_postcondition(emission, context) -> PostconditionResult`, walking the
declared clauses in order and reporting the first that fails, by id. `emission` is
the same `{"action": …, "price": …}` mapping the gates already receive, holding the
settled value rather than the proposal, so clause predicates keep the gate
predicates' exact shape — `(decision, context) -> bool`, matched by id.

New exception `GuardUnavailable(Exception)`, sibling to `SafetyViolation` rather
than a subclass: a question the guard could not answer is not a rule it answered
against, and a caller that catches one must not silently catch the other. It
carries the same `code` attribute.

**`proteins/guard/skill.py`** — expose `check_postcondition` as an intent; raise
`GuardUnavailable` instead of `SafetyViolation` for `SANCTIFICATION_UNAVAILABLE`,
so a lookup failure and a rule violation stop sharing a type.

**`membrane/main.py`** — call `check_postcondition` on the settled emission on
both the `emit` and `override` paths; on failure refuse with
`DECISION_OUTCOME_UNAVAILABLE` and `outcome_gate = POSTCONDITION_VIOLATION`; stamp
`issued_at`, `decision_id`, `request_id`, `override_scope` onto the verdict; widen
the `membrane_receipt` log line to carry the whole receipt; pass `request_id` down
to `safe_offer` so the jitter is session-stable.

Replace the override's `"I've reached my final limit for this item. My best offer
is $X."` (`:655`) with a neutral counter phrasing that does not announce a guard
trip, and the DLP override's `"I cannot disclose internal pricing details."`
(`:554`) likewise. Per Decision 10c this reduces distinguishability rather than
removing it, and the doc must say so rather than implying the message is now safe.

**`membrane/receipt.py`** — V2 content fields and version names; delete V0/V1
constants and `_PROSE_ONLY_GATES`; compute `unverifiable` instead of returning a
constant, always including `emission_content`; require `derivation` when
`outcome ∈ {EMIT, OVERRIDE}` and `ruleset_version` is non-empty; check
`override_scope` in both directions — `override` with `scope = "value"` and equal
hashes is a receipt describing a substitution that left no trace, and `override`
with `scope = "prose"` and **differing** hashes is a receipt claiming prose changed
the decidable content, which prose is defined not to reach. Both are failures; only
the first is caught today.

**`api-gateway/main.py`** — split `receipt_to_json` into the public renderer
(`version`, `canonical_prefix`) and the full one. Only the public renderer reaches
the HTTP response.

**`tools/verify_receipts.py`** — read JSONL from stdin or a path, pull `receipt`
objects out of `membrane_receipt` lines, run `verify()`, print totals: checked, ok,
failed with reasons, unattested, and the `unverifiable` categories seen. A `make`
target invokes it. Placed beside `distill_knowledge.py`, matching the existing
convention for repo tooling.

**`docs/DECISION_RECEIPT.md`** — record the audience decision; correct §7's claim
that a consumer can check the receipt independently; state that the receipt is
per-decision and attests nothing about a sequence; document the strategy collapse
and ψ; note that §3.6's "stop hiding the override" now holds for the auditor and
not for the client, and why.

## Error handling

Every path fails closed.

| condition | behaviour |
|---|---|
| ψ clause fails | `UNAVAILABLE` + `POSTCONDITION_VIOLATION`, `logger.error`, nothing emitted |
| ψ predicate raises | identical — an unevaluable post-condition is an unestablished one |
| `postcondition` block missing or malformed | `RulesetError` at `OutputGuard.__init__`, same as a gate mismatch |
| clause ids and predicates disagree | `RulesetError`, both directions |
| sanctification lookup fails | `UNAVAILABLE` + `SANCTIFICATION_UNAVAILABLE` — unchanged refusal, newly distinguishable from a violation |
| signing unavailable | unchanged: unsigned V2 is emitted, the decision is unaffected |
| receipt claims an unknown version | refused outright, no best-effort check — existing behaviour, now also rejecting V0/V1 |

A ψ failure turning a working negotiation into a refusal is the accepted cost. ψ
is exactly the conjunction the gates already claim to enforce; if it fires,
something is broken, and the found bug is proof that this is not hypothetical.

## Testing

- **`test_guard_postcondition.py`** — ψ holds on the `emit` path; **ψ holds on the
  `override` path**, which is the regression for the bug in *Why*; a violated ψ
  produces `UNAVAILABLE` and emits nothing; a raising predicate does the same.
- **Property test** over a grid of `(floor, internal_cost, m, proposed_price,
  request_id)`: either the emitted price satisfies ψ, or the decision was refused.
  This is the test that would have caught the bug, and the main reason ψ is
  executable rather than prose. It must include `internal_cost > floor`, every
  admissible `m` including `0.0` and values near `1.0`, and prices whose exact
  substitute does not land on a cent — the three cases the audit used to break the
  first draft of this design.
- **`test_guard_safe_offer.py`** — `safe_offer` is stable across calls within one
  `request_id` and differs across `request_id`s; the emitted price is never below
  the unjittered substitute; ψ holds for every jitter draw.
- **`test_guard_ruleset.py`** — digest pin updated; clause ids cross-checked both
  ways; a rule set carrying a per-gate `safe_price` key is **rejected** rather than
  ignored. That is new strictness, and deliberate: the key is exactly what a stale
  pre-collapse `ruleset.yaml` still carries, and silently ignoring it would let a
  file that describes two strategies load into an engine that implements one.
- **`test_receipt.py`** — V2 content fields and order; V0/V1 refused; `unverifiable`
  computed, always containing `emission_content`; `override_scope` checked in both
  directions; `derivation` required where the outcome implies it.
- **`test_receipt_transport.py`** — the gateway's public view carries only
  `version` and `canonical_prefix`, with explicit assertions on the **absence** of
  `outcome`, `outcome_gate` and the hashes.
- **`test_membrane_derivation.py`** — unchanged in intent; updated for the new
  outcome and fields. Replay still builds a fresh Membrane, registry and guard per
  run.
- **CLI test** over a fixture log containing one ok, one failing and one unsigned
  receipt.

## Rollout

Single branch, single format bump, no migration — no persisted receipts exist
(Decision 8). `make lint && make test` gates the merge. The frontend half of the
receipt work stays out of scope and is unaffected: it was never wired.

## Risks

- **ψ is wrong and refuses valid decisions.** This is the risk the audit landed on,
  and it was real: the first draft of this design refused the guard's own safe
  offer at the default configuration, from cent rounding alone. Mitigated now by
  `Decimal`, ceiling rounding, the multiplicative clause and a property test built
  from the cases that broke it — but the general shape of the risk survives any
  particular fix, because ψ is fail-closed and therefore every imprecision in it
  costs a live negotiation. Detectable immediately: `POSTCONDITION_VIOLATION` is
  loud and distinct.
- **The strategy collapse changes prices in production.** It does, upward, and
  that is the point — the old value could breach the margin rule. Jitter raises
  them a further 0–3%. Worth a note to whoever watches conversion rates.
- **Jitter is a mitigation, not a fix.** `ε` is public, so the floor is disclosed
  to within 3%, and a templated override message stays distinguishable from the
  model's own prose. Decision 10c records what would actually close the channel and
  why we are not doing it.
- **`issued_at` comes from our own clock and means nothing to a party that does
  not trust us.** Accepted: Decision 1 says that party is not the audience. If the
  audience changes, this field is the first thing that needs a nonce.
- **The receipt still cannot be checked against the decision** (`emission_content`).
  Unchanged by this work, now stated by the verifier itself rather than left for a
  reader to discover. Closing it remains `premise_hash`, still blocked on the same
  question.
