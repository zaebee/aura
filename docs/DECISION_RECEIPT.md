# Decision Receipt (AURA-RECEIPT-V2)

Status: **steps 1, 2, 3, 5, 6 and 7 built; step 4 deferred.** Adapted from VISION whitepaper v1.7.0
(Durov, 2026-05-05), chapters 4–6. This document records where we follow that spec and — more
importantly — the places where our domain forces us to diverge from it. Sections marked
*Implemented* describe code; the rest is still design.

> **Rewritten 2026-08-12, after V2 shipped.** The version of this document that described
> `AURA-RECEIPT-V1` claimed several properties the code does not have, and one of them — §7's claim
> that a consumer can check a receipt independently — was false the day it was written. Building V2
> also turned up a live bug in the guard that this document's own omission had hidden (§3.8). Where
> a claim here used to be aspirational it now says so, and where something is bounded rather than
> closed it says bounded.

## 1. What the receipt is for

Every `Intent` that leaves the Membrane carries a small, self-contained, signed artefact recording:

- the decision was produced under a **declared rule set at a declared version**;
- the **deterministic gates actually ran**, in order, and which one fired;
- the proposal and the emission are each pinned by a digest, so anyone holding the receipt **and**
  the decision can see whether either changed, and whether the Membrane intervened between them;
- **which decision, in which session, at what time** — `decision_id`, `request_id`, `issued_at`.

…without carrying `floor_price`, `internal_cost`, or `min_profit_margin`. The receipt carries
hashes, not premises.

Note what is *not* in that list. A reader holding a receipt cannot establish that `claim_hash`
digests a decision that ever happened, because nothing they hold is the decision. See §7, which used
to claim the opposite.

Non-goal: proving the *Transformer* (LLM) reasoned well. The receipt attests the **Membrane's**
verdict over the LLM's proposal. That boundary is the whole point — see §5.

## 1.1 Who the receipt is for

**The receipt is addressed to an auditor, not to the counterparty we negotiate against.** This was
decided during the V2 design and it is the premise the rest of this document rests on; read
everything below as answering "what does an auditor need", not "what can we hand a stranger".

The reason is that we pay the full cost of counterparty verification — EIP-712, a self-describing
domain, a `verify()` needing no key or configuration, an address resolvable through ERC-8004 — and
cannot deliver the thing those buy. A counterparty-facing verifier needs the original input, a
freshness challenge it chose, and a transparency log. We have none of the three: `verify()` receives
the receipt and nothing else, `issued_at` is our own clock, and no receipt is published anywhere a
third party can watch.

Three things follow that read as arbitrary without this decision, and follow necessarily with it:

- **Field selection.** `outcome_gate` names the rule that fired; the rule set maps that gate to a
  substitute-price strategy; the substituted price is already in the response. Together those
  reconstruct most of the floor. An auditor may have all of it. A counterparty may not.
- **The gateway trim (§3.6, §7).** The HTTP response carries **no receipt at all**, in any shape.
  What it carries instead is `dispute_token`: a random UUID minted per decision, logged beside the
  receipt, which the auditor resolves. Trimming to `version` + `canonical_prefix` was the first
  attempt and did not hold — see §3.4 for what a counterparty recovered from those two fields, and
  for the narrower claim that survives.
- **Freshness by timestamp rather than nonce (§3.7).** A nonce needs a challenge from the relying
  party. The audience decision removes the relying party, and adding one would change the
  `/v1/negotiate` contract and every synapse that speaks it.

If the audience ever changes, `issued_at` is the first field that needs replacing, and the removal
in §3.6 is the first decision that needs reopening.

## 2. Where it is minted

`HiveMetabolism.execute()` step 4, inside `HiveMembrane.inspect_outbound()`, which is already our
verification boundary: it is the last deterministic checkpoint before `Connector.act()`.

```
signal → M(in) → A(perceive) → T(think) → M(out) ⇐ RECEIPT MINTED HERE → C(act) → G(pulse)
```

The receipt is `Intent.receipt`, a typed `DecisionReceipt` in
`aura/core/v1/metabolism.proto`. It is minted after the verdict is settled and signed by the
transaction protein, which owns the key; a receipt that cannot be signed is emitted unsigned rather
than costing the decision.

One step now sits between the verdict and the mint:

```
M(out) ├─ guard.validate_decision(proposal, ctx)   gates → derivation
       ├─ [on failure] guard.safe_offer(ctx)       one substitute strategy (§3.3)
       ├─ guard.check_postcondition(emitted, ctx)  ψ, on BOTH paths (§3.8)
       └─ mint(claim, emission, verdict) → sign → Intent.receipt
```

ψ runs after the emitted value is settled and before the receipt is minted, so a post-condition
failure becomes the decision's recorded outcome rather than something discovered after a receipt has
already asserted otherwise.

## 3. Wire format

`DecisionReceipt` is a proto message; the canonical form below is what gets hashed and signed, not
a transport encoding. The eleven **content fields** are joined by `\n` in exactly this order — order
is part of canonicalisation, and reordering produces a different prefix and fails verification.

```
version                          AURA-RECEIPT-V2 | AURA-RECEIPT-V2-UNSIGNED
issued_at                        RFC3339 UTC, second precision
decision_id                      Intent.identifier of the emission
request_id                       the negotiation session
claim_hash                       <hex64>
ruleset_version                  <family>@<major>.<minor>.<patch>+<hex16>
derivation.derivation_hash       <hex64>, empty string when derivation is unset
emission_hash                    <hex64>
outcome                          emit | override | refuse | unavailable
outcome_gate                     the first gate that fired
override_scope                   prose | value, empty unless outcome is override
```

Three fields ride alongside the signed content rather than inside it: `derivation.gate_sequence`
(the witness `derivation_hash` already commits to), `canonical_prefix` (a handle, derived from the
content), and `signature` (which cannot commit to itself).

`premise_hash` and `policy_stamp` are **not** here. They are reserved — proto field numbers 9 and
10, by name — and §3.1 and §3.5 record why each is still waiting on a decision rather than on code.
Two things this document once listed as receipt lines therefore do not exist, and a reader who
expected them should read those sections rather than assume an omission.

### 3.1 `premise-hash`

`SHA256(salt ‖ canon(premises))` over the canonical, key-sorted premise set consumed from `Context`:

| premise key | source | visibility |
|---|---|---|
| `ctx.id` | `Context.identifier` | public |
| `floor_price` | `Context.metadata` | **hidden** |
| `internal_cost` | `Context.metadata` | **hidden** |
| `bid` | `HiveContextData.offer` | known to counterparty |
| `item` | `HiveContextData.item_identifier` | public |
| `health` | `Context.system_health` | public |

**Deferred — and the analysis changed what it would have to be.** The premise set is low-entropy:
`floor_price` is a two-decimal number over a bounded range, ~10⁷ candidates on its own, ~10¹⁴ with
`internal_cost` — hours on one GPU, and far less once you bound the range from the offers you have
already seen.

So **anyone holding the salt can recover the premises by enumeration**. The salt is exactly as
secret as `floor_price` itself, which means the premise hash can *never* be a counterparty-verifiable
field: verification and secrecy are mutually exclusive here. It can only be a commitment we open to a
party already trusted with the floor.

That is a different threat from VISION's. §8.7.1 salts against **linkage** — "an adversary who
observes a sequence of receipts may infer that two receipts consume the same premise set" — on
premises assumed high-entropy, and records the salt *in the policy stamp*, where it is public. For
our threat, inversion, their design accomplishes nothing.

If built, the right primitive is a **per-receipt random nonce stored alongside the receipt**, not a
configured salt: no long-lived secret to rotate, nothing whose leak retroactively exposes the whole
history, and opening is selective — reveal `(nonce, premises)` for the one deal under dispute. Use
HMAC rather than `SHA256(salt ‖ data)`; there is no reason to hand-roll a keyed digest.

The prerequisite is not cryptographic: a commitment you cannot open is a random number, so this needs
receipts persisted where an auditor can read them. **The question to answer before writing any of it
is who opens it and when.** Without a concrete dispute or audit flow, this is ceremony.

### 3.2 `claim-hash`

VISION's `graph-hash` names a typed constraint graph. **We do not have one** and this document will
not pretend otherwise. The honest analog is a canonical serialisation of what was being decided:

```
canon(action=counter; item=<id>; price=<decimal2>; currency=<ISO4217>)
```

i.e. the LLM's proposal reduced to its decidable content, with `reasoning`/`message`/`thought`
stripped — they are prose and must not enter the hash, or determinism dies. This is a genuine
downgrade from VISION's Layer 1 and the main thing that would have to be built to claim the
"neuro-symbolic" label rather than "attested guard".

**`currency` is in the claim as of V2, and until V2 it was not.** This document promised the field
in both §3.2 and §4 while `canonical_claim` emitted `action;item;price` — so two decisions
denominated differently digested identically, and the doc described a receipt nobody was minting.
The proto now carries `currency_code` on `NegotiationOffer` and `NegotiationIntent`, the aggregator
sites populate it, and the Membrane stamps it from the Context before claim and emission can
diverge. An unset currency renders empty rather than defaulting to one: a denomination nobody stated
is not USD, and inventing one would make two different decisions share a digest. Two sites
(perception, telegram) genuinely have no source for it and pass the empty string with a comment
saying so.

**What `claim_hash` digests is the proposal as normalised by the Membrane, not the byte-exact
object the Transformer handed over.** The stamping above is a mutation of the caller's Intent, and it
happens before the claim is taken. That is deliberate — the denomination is a property of the request
and the model never had a say in it, so stamping it after the claim would make claim and emission
disagree over a field nothing decided — but it means the baseline the two digests are taken against
is ours, one normalisation deep. Three fields are normalised today: `currency_code` (above),
`identifier` (named when nothing upstream did — outside the canonical claim, so it moves no digest),
and `price`, **quantised to cents**.

The first two are properties of the request that nothing decided. **The price is not** — it is the
model's own decision, and quantising moves it by up to half a cent. It is normalised anyway, for a
different reason: the claim renders `price` at `.2f`, so without it the gates decide at a precision
the digest cannot express, and a proposal a fraction of a cent below the margin threshold is
substituted onto its own cent — claim and emission digesting alike while `override_scope` says
`value`, the combination §3.6 and `verify()` refuse. Quantising first makes the gate, ψ, the
substitute and both digests read one value.

That closes the collision for every gate that refuses a *price*: G1, G2 and G4 each imply the
proposal sits strictly below a threshold the substitute is ceilinged above, so the two cannot render
to the same cent. It does not close it for a gate that refuses the *configuration* — G3 fires at any
price — which is why G3 now refuses outright rather than substituting (§3.6), and why an override
whose emitted cent equals the proposed one is not recorded as an override at all.

Anything else added here
widens the gap between "what the model proposed" and "what the claim says the model proposed", which
is the sentence this paragraph exists to keep honest.

Note also what the claim does **not** identify: a sequence. Each receipt describes one decision. Two
receipts from the same negotiation are related only through `request_id`, which is an identifier we
chose and not a chain — nothing in a receipt commits to its predecessor, so a receipt cannot attest
that a round of a negotiation was not dropped or reordered.

**That downgrade has a compensating side, and it is worth stating because it explains why the rest
of this document was cheap to build.** Tuan & Sanyal (2026), *Ontology-Constrained Neural Reasoning
in Enterprise Agentic Systems* ([arXiv:2604.00555](https://arxiv.org/abs/2604.00555)), survey
enterprise agent platforms and find that they constrain agent **inputs** — context assembly, tool
discovery, governance gates — but do not
validate **outputs** against the same definitions, so an agent can receive perfect context and still
emit a constraint-violating answer. They call this *asymmetric neurosymbolic coupling* and rank it
on a maturity scale:

| level | what the ontology does |
|---|---|
| L1 | supplies prompt context (input side) |
| L2 | filters which tools are available |
| L3 | gates approvals during execution |
| **L4** | **validates the output after generation** |
| L5 | closed loop: also evolves from experience |

Their own production platform — 650+ agents across 22 verticals — runs at L2–L3. L4 is described as
"the primary research frontier and is not yet implemented".

The Membrane is L4: `inspect_outbound` judges what the Transformer produced, after it produced it.
The receipt goes a step past their L4 sketch by recording *which* rules judged it and signing that.

**Why it was tractable here and is a research problem there** is the interesting part, and it is the
flip side of not having a constraint graph. Their proposed L4 validates *free text* — checking that
terms, metrics and regulatory claims in a natural-language answer are defined in the ontology — and
their own threats-to-validity section concedes the difficulty: it "requires translating free-text LLM
outputs into OWL-compatible representations — itself an error-prone process".

Our Transformer does not emit prose to be judged. It emits a typed `Intent`, and the canonical form
above deliberately strips the prose it does carry. **There is no translation step to get wrong**, so
the validation that paper positions as a frontier is, in this shape, ordinary work. That is a
property of the domain rather than a cleverness: a negotiation decision reduces to an action and a
price, where a clinical or regulatory answer does not.

One of their empirical findings points the same way. Ontological grounding helps most where the
model's parametric knowledge is weakest — they measure roughly double the lift on
Vietnamese-localised domains versus English ones. Hidden floor prices, our own rule set and the
receipt format are all things no model can know from its weights, which is the regime where this
kind of layer earns its keep. Caveat on their numbers: 1,800 runs across three models with large
effect sizes, but scored by an LLM judge rather than domain experts, and measured on one platform.

### 3.3 `ruleset-version`

**Implemented.** `guard/negotiation@2.0.0+6b8b5d6db3e6e351` — family, semver, and a digest over the
declared rules in `proteins/guard/ruleset.yaml`.

The digest is taken over the **parsed structure**, not the file bytes. Hashing the source was the
obvious implementation and the wrong one: a reflowed comment would mint a new rule-set version, and
a version that changes without the rules changing is noise a verifier learns to ignore — which is
precisely when it stops catching the change that mattered. Keys are sorted; list order is preserved,
because gate order decides which reason a decision is refused under and is therefore part of the
rules.

> **Correction to an earlier draft of this document.** The first sketch put a `thresholds:` block
> inside `ruleset.yaml`. That is wrong on VISION's own terms: §4.2.3 makes the threshold "a
> configurable predicate on the receipt, not a property of the layer", and operator-tunable values
> belong in the **policy stamp** (§3.5), not the rule set. Folding them in would mean every operator
> who turns a knob forks the rule set, and two deployments running identical rules would cite
> different versions. `min_profit_margin` and friends stay in `SafetySettings`. The practical
> benefit is that extracting the rules changed no configuration semantics — the env override still
> works.

What the rule set holds is the gate list in evaluation order, each with the code it emits and the
premise keys it consumes; **one** substitute-price strategy for the whole set; and the
post-condition the set guarantees about what it lets out (§3.8):

```yaml
family: guard/negotiation
version: 2.0.0

safe_price: safe_offer          # one strategy for the set, not one per gate

postcondition:
  id: PSI_NEGOTIATION_V1
  clauses:
    - {id: PSI_PRICE_POSITIVE, expr: "price > 0",                consumes: [price]}
    - {id: PSI_ABOVE_FLOOR,    expr: "price >= floor_price",     consumes: [price, floor_price]}
    - {id: PSI_MIN_MARGIN,     expr: "price * (1 - min_profit_margin) >= internal_cost",
       consumes: [price, internal_cost]}

gates:
  - {id: G1_PRICE_POSITIVE,   code: INVALID_PRICE,         consumes: [price]}
  - {id: G2_FLOOR_VIOLATION,  code: FLOOR_PRICE_VIOLATION, consumes: [price, floor_price]}
  - {id: G3_SETTINGS_PRESENT, code: SETTINGS_MISSING,      consumes: []}   # fail-closed
  - {id: G4_MARGIN_VIOLATION, code: MIN_MARGIN_VIOLATION,  consumes: [price, internal_cost]}
```

**The per-gate `safe_price` key is gone, and its removal is why the digest moved.** V1 declared two
strategies, `floor_markup` and `margin`, and let each gate pick one. Since the collapsed strategy is
`max(floor × 1.05, max(floor, internal_cost) / (1 − m))` it is **always ≥** what `margin` produced,
so the two never differed in guarantee — they only differed in which one a gate happened to name.
Two strategies with indistinguishable guarantees is the crack the bug in §3.8 came through. The
semver bump to `2.0.0` is deliberate on top of the digest move, not a substitute for it: the digest
covers the declared structure and would have moved anyway, which is exactly the property the caveat
at the end of this section says predicate *bodies* do not have.

A rule set that still carries a per-gate `safe_price` is **rejected at construction**, not ignored.
That is new strictness and it is deliberate: the key is precisely what a stale pre-collapse
`ruleset.yaml` carries, and silently ignoring it would let a file describing two strategies load
into an engine implementing one.

Two properties keep the version honest rather than decorative:

- **The declaration and the implementation cross-check, both ways, for gates and for ψ clauses.**
  `OutputGuard.__init__` calls `Ruleset.validate_against(gate_ids(), clause_ids())` and refuses to
  construct on a mismatch. A declared gate or clause with no predicate would never fire while the
  rule set advertises it; a predicate that is not declared runs outside anything a receipt can
  account for.
- **The shipped digest is pinned in a test.** Editing `ruleset.yaml` fails `test_guard_ruleset.py`
  until the pin is updated in the same commit — which is the moment to ask whether `version` should
  be bumped too.

The gate order shipped here is not a preference; it reproduces the order the if-chain applied, so
decisions already in flight keep the reason they were refused under. Note `G1_DLP_DISCLOSURE` and
`G2_ACTION_SCOPE` from the earlier sketch are absent: DLP lives in the Membrane rather than the
guard engine, and action scope is a precondition for judging at all rather than a gate that can
fail. Both would need a second family to be declared honestly.

**Still a partial content-address.** The digest covers the declared structure, not the predicate
bodies — those are still Python, and the `expr` strings beside them are text for a human reader and
for the digest, never evaluated. A change to what `_gate_margin_violation` or `_clause_min_margin`
computes does not move the digest, so predicate edits require a manual `version` bump that nothing
enforces. VISION §4.2.4 wants the implementation content-addressed by the rule-set hash; we are not
there. ψ inherits this limit exactly as the gates do: `PSI_MIN_MARGIN` names a clause, and only the
Python behind it decides what that clause means.

`trade` and `rwa_vault` params get sibling families (`guard/trade@…`, `guard/rwa@…`) with their own
gate lists (`KYC_PASSED`, `RISK_THRESHOLD`, `HILL_CEILING`, `WALLET_SANCTIFIED`).

### 3.4 `derivation-hash` and `gate-sequence`

**Implemented**, as `Intent.derivation` (`DecisionDerivation`). Our derivation *is* the ordered gate
evaluation. Each record:

```
<gate-id>:<pass|fail>:<premise-keys-consumed>
```

Records are joined by ASCII unit separator `0x1F` — it cannot occur in a gate id or a premise key, so
the canonical form needs no escaping rule. A real sequence, for a price below floor:

```
G1_PRICE_POSITIVE:pass:price␟G2_FLOOR_VIOLATION:fail:price,floor_price
```

`derivation-hash = SHA256(gate-sequence)`, lowercase hex64. The two fields are redundant by design
(VISION §5.1.6bis): a reader does one hash compare for structural integrity, and only then pays for
replay.

**The record names premise keys, never values.** This is the property that makes it publishable, and
it is asserted directly — `test_no_hidden_number_appears_in_the_sequence` checks that neither the
floor, the internal cost, nor the price appears anywhere in the sequence that reaches the Intent.
Two consequences worth stating as properties, both tested:

- Two decisions differing only in price derive **identically**. Distinguishing them is the emission
  digest's job (§3.6). Keeping values out of this field is what stops *this field* being a value
  oracle.
- The digest moves when the *steps* move: raising the floor so that `G2` fails where it passed
  changes it, but changing the floor while every gate still passes does not.

**Gates short-circuit, and the sequence ends where evaluation did.** A reader can see that the gates
after the failure were never consulted. This pairs with §4.3.5's reasoning behind `outcome_gate`
recording only the first failure: enumerating every gate that *would* have fired gives an adversary
an oracle over the policy configuration, and the boundary they would map is `floor_price`. It is also
how the bug in §3.8 stayed hidden — a gate that never ran cannot judge anything, and until ψ existed
nothing else did either.

**Nothing derived is not an empty derivation.** When no declared gate ran — a decision outside the
guard's scope, an unwired Membrane, or one of the Membrane's own checks — the field is left unset
rather than carrying the hash of an empty string. Hashing nothing would assert a derivation that
never happened, and a verifier could reproduce that digest and conclude, falsely, that gates ran.

Note this covers the *guard's declared gates only*. KYC, trade-risk and DLP are Membrane-level checks
that no rule set declares, so they cannot be recorded as gates without inventing ids nothing versions
(§3.3). Those paths refuse with an `outcome_gate` and no derivation, which is the honest report.

#### The leak this field closes, and the one it does not

**"You cannot probe it for the floor" holds for this field and not for the channel, and an earlier
draft of this document ran the two together.** The derivation is clean. The counter-offer beside it
is not: when a gate fires, the Membrane substitutes `safe_offer(context)`, and that price is a
function of the hidden floor. It reaches the counterparty as `proposed_price` on every counter,
whatever a receipt does or does not say. No amount of trimming the receipt touches it.

What V2 does about it is bound the disclosure, not close it:

- **Per-session jitter.** `safe_offer` multiplies by `(1 + j)` before rounding up, where
  `j = ε · HMAC(process_secret, request_id) / 2²⁵⁶` and `ε = 0.03`. Constant within a session, so
  repeated rounds within one negotiation cannot average it away. **Across sessions it decays to
  nothing, and an earlier draft of this bullet claimed the opposite.** Independent draws per session
  are exactly what a corpus averages out: the standard error of the mean over `N` observations is
  `base · ε / √(12N)`, about **0.09% of the base at `N = 100`**. So the real bound is 3% per
  observation against a counterparty who sees one, decaying toward zero against a repeat
  counterparty on the same item. `(1 + j) ≥ 1` and the rounding is a ceiling, so jitter cannot push
  a price through ψ. The
  secret is process-lifetime random rather than configured — nothing needs to reproduce the price,
  because ψ checks the value, which is the whole reason ψ is executable (§3.8). An empty `request_id`
  draws zero rather than noise nobody can reproduce: a caller with no session gets the deterministic
  price, and the absence shows in the number rather than hiding behind it.
- **Neutral prose at both substitution points.** The override used to emit `"I've reached my final
  limit for this item. My best offer is $X."` and the DLP block `"I cannot disclose internal pricing
  details."` — each of which announced that a guard had fired. Both now read as an ordinary counter.

**`ε` is a source constant and therefore public, so the counterparty still learns the floor to within
3%.** That bound holds only because every floor-derived price is born in the guard, which applies the
markup and the jitter. The rules-based strategy used to break it: with `llm.model == "rule"` a
below-floor bid was countered at `floor_price` exactly, and the message said the number out loud —
a 0% bound on a path the DLP check could not see, because it scans for the literal token
`floor_price` rather than for its value. That strategy no longer prices at all; it proposes the bid
back and lets the floor gate fire, so the substitute comes from the same place as every other one.
And neutralising the message reduces distinguishability rather than removing it: a templated
counter still reads differently from the model's own prose, and closing that gap properly means
having the model phrase the substituted price, which is its own piece of work.

**Removing the receipt from the response does not close this channel either, and it is worth saying
exactly what it does close.** V2 first trimmed the HTTP response to `version` and
`canonical_prefix`; it now carries no receipt at all (§7). The prefix had to go because it is
invertible: it is a 64-bit digest over eleven content fields, of which the counterparty holds
`session_token` (the request id, in plaintext) and the price, and can guess the rest from the
published rule set version and a bounded price grid. A reviewer wrote the attack from the
counterparty's side and recovered `proposed_price = 873.45` — **the model's own number, below the
floor** — together with `gate = FLOOR_PRICE_VIOLATION`, in 7.3M SHA-256 and 8.1 seconds on one
single-threaded CPython process. That is the §5 step-4 enumeration argument about `premise_hash`,
applied to the field that was actually on the wire. `version` was worse: it flips between
`AURA-RECEIPT-V2` and `AURA-RECEIPT-V2-UNSIGNED` per call, because `_attest` degrades to the
unsigned format on **any** signing failure — so a client polling it read a live feed of whether our
transaction protein was reachable — and `receipt: null` versus an object reported whether minting
had happened at all.

So the claim is narrow, and it is not closure:

- **What removal closes:** one-shot recovery, from a single response, of the model's own proposed
  price and of which gate fired. Before, one counter was enough.
- **What it does not close:** `proposed_price` is still in the response on every counter, so the
  bound above still holds and still decays with `N`. Timing is a further residual — the override
  path makes extra registry round-trips, so a patient counterparty can distinguish an overridden
  counter from an ordinary one without reading a word of it.
- **What is not lost:** nothing evidential. The counterparty received the prefix *without* the
  signature block, so they could never tell a real receipt from one we invented; it was never
  probative in their hands. `dispute_token` is the handle it was supposed to be — random, per
  decision, with no preimage to enumerate — and the auditor resolves it against the log.

The only design that closes the channel outright is **refusing instead of countering** — which §3.6
declines, on product grounds, deliberately. That is the trade: we keep the negotiation alive and pay
for it with a bounded leak of the floor. Bounded, not closed. Stating it is better than implying it
away.

### 3.5 `policy-stamp`

Here we diverge from VISION hardest. Their policy stamp is public by design so a consumer can audit
the operator's settings before relying on a receipt. **Our policy values are themselves the hidden
knowledge**: publishing `min_profit_margin=0.10` next to an emitted price hands over
`floor ≈ price·(1−margin)` — the exact leak the DLP gate exists to prevent.

So the stamp splits:

```
policy-stamp:  gates=6;jurisdiction=XXX;salt-commit=<hex16>;thresholds=<hex16>;schema=1
```

- **public**: gate count, jurisdiction (ISO-3166-1 alpha-3), salt commitment, stamp schema version;
- **committed**: `thresholds=<hex16>` — a salted hash of the ordered threshold vector.

The counterparty gets a binding commitment that our thresholds were fixed *before* the decision and
have not been retrofitted. An auditor holding the salt gets full disclosure. Nobody gets the margin.

**Not built.** Proto field 10 is reserved for it by name. The split above is written for a
counterparty audience, which §1.1 has since decided against, so whoever builds this should reread it
against that decision first — an auditor we already trust with the floor does not need a commitment
scheme to be told the margin. The sketch also predates the current rule set: it says `gates=6`,
and there are four.

### 3.6 `emission-hash` and `outcome`

`emission-hash = SHA256(canon(emitted Intent body))` — same field selection as `claim-hash`, applied
to the final Intent rather than the LLM's proposal. Comparing the two is exactly how a reader sees
that the Membrane intervened.

`outcome` is our third divergence. VISION has two terminal states, emit and refuse, and argues
forcefully that approximating instead of refusing is the failure mode of probabilistic systems. We
have a third state and we ship it deliberately: `_override_with_safe_offer()` **replaces** the LLM's
price with `calculate_safe_price()` and continues the negotiation. That is a product decision, not
an accident — dropping the conversation on every guard trip would be worse for the user.

The fix is not to remove the override. It is to **stop hiding it from the auditor** — which is a
narrower claim than the one this section used to make, and §1.1 is why. The override is a typed,
signed fact on the receipt an auditor reads. It is not on the HTTP response, which carries no
receipt in any shape (§7), and §3.4 states what that does and does not close.

| outcome | meaning | `claim_hash` vs `emission_hash` |
|---|---|---|
| `emit` | LLM proposal passed all gates unmodified | equal |
| `override` | a gate fired; Membrane substituted a deterministic safe value | differ, unless the scope is `prose` |
| `refuse` | a gate fired; the action was rejected (KYC failure, high-risk trade) | emission is the reason |
| `unavailable` | **no verdict could be established**; nothing was emitted | — |

**`unavailable` is new in V2, and it is not a gate failure.** A gate firing means a rule judged the
proposal. ψ failing, or a fact the guard needed being unreachable, means *we* are broken, and the
two send an operator to different places — one to the offer, one to the dependency that is down.
AR4SI (`draft-ietf-rats-ar4si`) separates them the same way: its `-1` "verifier malfunction" is not
a member of the tier that carries appraisal failures. It is readable from `outcome` rather than by
parsing `outcome_gate` strings, and the same split runs through the code: `GuardUnavailable` is a
sibling of `SafetyViolation`, not a subclass, so a caller catching one cannot silently catch the
other. `SANCTIFICATION_UNAVAILABLE` — a lookup that failed, not a rule that judged — moved onto it.

**Implemented.** The override used to be recorded only in `_record_intervention()` telemetry and a
`[MEMBRANE: …]` suffix on free-text `reasoning`.

Three limits worth stating rather than discovering later:

- **A prose-only override shows equal hashes**, and `override_scope` is how a reader tells that from
  a lie. The DLP gate rewrites the message and nothing else, and prose is deliberately outside the
  claim (§3.2), so a DLP-only override is visible through `outcome` but not through the digests.
  Bringing prose into the hash would cost determinism on every decision to catch this one case.

  V1 handled this with `_PROSE_ONLY_GATES`, a hardcoded list inside `verify` naming which gates were
  prose-only — a list that goes stale the moment someone adds a prose-only gate and never tells the
  verifier. V2 deletes it. The receipt now *says* which kind of intervention happened, in a signed
  field, and `verify` checks the pairing in both directions: an override scoped to `value` whose
  digests agree describes a substitution that left no trace, and one scoped to `prose` whose digests
  differ describes prose reaching the decidable content, which prose is defined not to do. Both are
  failures; V1 caught only the first.

  **`override_scope` answers "did the decidable content change", and `outcome_gate` answers "which
  rule explains this outcome". They are different questions and they accumulate differently.** V2
  first tied them together — scope was written in the same first-wins call as the gate — and that
  produced a receipt the Membrane minted and its own verifier refused: a message tripping DLP
  recorded `prose`, the floor gate then substituted the price, and `verify` rejects `prose` beside
  differing digests. Ordinary traffic, and `make verify-receipts` exited 1 on it.

  Scope is now **monotonic toward `value`**: it starts empty, a prose-only intervention raises it to
  `prose`, and a price substitution sets `value` unconditionally, whichever gate is named. Every
  intervention reaches it, because the question is about all of them together. The gate stays
  first-wins **within an outcome class** and resets when the class changes — first-wins *forever*
  shipped `outcome = unavailable` with `outcome_gate = DLP_BLOCK`, "unavailable because DLP", which
  the error table in §3.8 contradicts and which `verify` does not catch, because it checks no
  gate/outcome coherence for `unavailable`.

  That resolution is only sound because G4 and `PSI_MIN_MARGIN` now decide the margin rule the same
  way (§3.8). "`value` scope with equal digests is a substitution that left no trace" reads as a
  failure only if a gate that fires implies a ψ that would have failed; while G4 used a binary-float
  ratio against the raw setting and ψ used a Decimal product against the clamped one, 9,444 of a
  1.6M-case scan broke exactly that implication.

  It needs one more thing, and the branch shipped without it once. That argument covers gates that
  refuse a **price** — G1, G2 and G4, each of which implies the proposal is strictly under a
  threshold the substitute is ceilinged above, so the two cannot render to the same cent. **G3
  refuses the configuration, not the price**, and fires at any price at all. Substituting on it also
  meant pricing with the default margin — answering with the very formula the gate had just declared
  unevaluable, which `ruleset.yaml` says must not happen. Since the substitute is a fixed cent within
  a session, a model echoing the Membrane's own last counter — ordinary convergence — proposed
  exactly it and minted `value` scope with equal digests, deterministically. G3 now refuses outright.

  Read that as a claim about the gate, not about the deployment. Gates stop at the first failure, so
  G3 is only *reached* when G1 and G2 pass: a below-floor or non-positive proposal on a misconfigured
  deployment is still answered, priced by the default-margin formula, and `ruleset.yaml`'s "must not
  answer at all" is honoured only for proposals that clear the price gates. That cannot reopen the
  collision — a proposal strictly under the floor cannot share a cent with a substitute ceilinged
  at-or-above it — so what remains is the narrower point that a deployment which cannot read its own
  margin still trades on those paths. Closing it means ordering G3 ahead of the price gates, which
  changes the rule set's digest and therefore `ruleset_version` on every receipt: a versioned change
  of its own, deliberately not folded in here.
  Independently of that, an override whose emitted cent equals the proposed one is not recorded as an
  override: a substitution that moves nothing is not a substitution, and the invariant holds when a
  fifth gate is added rather than relying on the next author to rederive why it held.

  `override_scope` is a property recomputed from the outcome rather than a field a call site sets,
  so it is structurally empty whenever the outcome is not `override` — that half of the invariant
  cannot be violated by any call site. The other half is by construction: the `ValueError` that
  catches an `override` recorded with no scope fires on **every** `override` call, not only the one
  that establishes the gate, because with a monotonic scope the second call is precisely what raises
  a decision to `value`. When it does fire it still **escapes**: neither `inspect_outbound` nor
  `MetabolicLoop.execute` wraps the Membrane call, so the exception leaves the cycle and the
  negotiation is lost rather than refused — the same failure `_context_number` exists to prevent for
  a different `ValueError` in the same file, and the wrong failure for the component whose job is to
  be the thing that does not let a bad decision out. No call site reaches it today, and the note is
  here so the next person adding an override path knows they are the case it was written for.

- **`refuse` receipts carry no derivation.** VISION §5.1.4 wants a real digest there, since a
  refusal is a closed derivation onto the refusal symbol. Ours are Membrane-level checks (KYC,
  trade risk) that no rule set declares, so there are no gate ids to record (§3.3). They carry an
  `outcome_gate` and an empty derivation, which is honest but is a gap against the spec. A witness
  for the refusal path needs a second rule-set family and its own spec.

- **An `override` emission used to drop two fields that were never in question.** The replacement
  Intent the safe-offer path builds carried the substituted price and a message and neither
  `item_identifier` nor `currency_code`, so a JPY negotiation emitted
  `action=counter;item=;price=111.12;currency=` against a claim that named both. `verify` did not
  fail — a `value` scope only needs the digests to differ, which the price delta already supplies —
  but a reader diffing claim against emission saw more change than there was. Fixed where the
  replacement is built. Note the ordering that made it worth doing *with* the G4/ψ fix rather than
  before it: while the gate and ψ could disagree, those dropped fields were part of what kept the
  digests apart, and carrying them forward on their own would have recreated the contradiction above
  on a decision whose substitute happened to equal the proposal.

### 3.7 `signature` and `canonical-prefix`

**Implemented.** EIP-712 over the receipt's content fields, signed with the agent's existing
**EVM key** — not the Ed25519 scheme this document first sketched.

The reason is key distribution, not convenience. **A signature under a key nobody can attribute is
decoration.** Signing is the easy half; giving a reader a way to learn that the key is ours is the
hard one, and the EVM identity already has an answer — the recovered address resolves against the
ERC-8004 identity registry. A fresh Ed25519 key would have had no such story, and inventing one is a
larger piece of work than all of step 5.

That argument was originally made about a counterparty. §1.1 has since decided the reader is an
auditor, and the argument survives the change intact but buys less: an auditor could have been given
a key out of band. It is a cost already paid rather than one worth paying again — and if the audience
widens later, this is the piece that is already right.

**The cost, stated plainly: the EVM key is a spending key.** The same `EVMProvider` that signs
receipts also does `transfer_usdc`. The mitigation that matters is domain separation, which is
exactly what EIP-712 domains are for:

```python
domain = {"name": "AuraDecisionReceipt", "version": "1", "chainId": <id>}
#         ^ not "HackathonRiskRouter", and no verifyingContract
```

Different domain separator means a receipt signature is **not** a valid `TradeIntent` authorisation
and a trade authorisation is not a valid receipt. `verifyingContract` is absent rather than zeroed —
a receipt has no contract — which makes the domain structurally different, not merely renamed.

The `ReceiptSignature` message is self-describing: scheme, domain, domain version, chain id, signer,
signature. A verifier rebuilds the domain from the receipt alone and needs no out-of-band
configuration, which is what VISION §5.2.2 means by a receipt being self-contained for replay.

**Two formats, not one format with a flag.** `AURA-RECEIPT-V2` is signed; `AURA-RECEIPT-V2-UNSIGNED`
is what a deployment with no key configured honestly produces. Separate names so a consumer written
against the signed format cannot be satisfied by a downgrade, and `verify` refuses a version it does
not recognise rather than best-effort checking it. `VerificationResult.attested` is true only when a
signature was present *and* recovered to the signer the receipt claims.

**The number is the generation; the suffix is attestation.** V0 and V1 read as two successive
formats and were not — they were one format signed and unsigned, with the generation number carrying
information that belonged in the suffix. V2 is the first real generation bump, and it exists because
of what entered the *signed* content:

| field | why it is signed |
|---|---|
| `issued_at` | freshness, by RFC 9334 §10's synchronized-clock route. Our clock, so it means nothing to a party that does not trust us — §1.1 says that party is not the reader. |
| `decision_id` | the `Intent.identifier` of the emission, carried across the override path by `_replacing`. Assigned by the Membrane when nothing upstream did — and until this branch, nothing ever did: no producer on the negotiation path set `Intent.identifier`, so every receipt signed an **empty** `decision_id`, attesting the field's absence under a format whose whole justification is the row below. |
| `request_id` | the negotiation session, so an auditor can group a sequence of decisions. |
| `override_scope` | see §3.6 — the field that replaced a hardcoded gate list inside the verifier. |

Without the first three a receipt described an *equivalence class* of decisions rather than a
decision: two deals for the same item at the same price under the same rules produced a
byte-identical receipt, signature included, and an auditor could reconcile neither against anything.
Binding that is not signed is decorative — anyone can rewrite it — so adding these fields necessarily
changed the signed content, and there is no variant of this change that leaves the format generation
alone.

**V0 and V1 are deleted, not deprecated.** No persisted receipt exists anywhere in the old shape:
until V2 the log line carried five scalar fields rather than a document, and the bee-keeper half of
step 6 was never built (§6). There is no corpus to migrate, so `verify` refuses the old version names
outright.

**Signing never costs a decision.** The decision is already made and already safe by the time the
Membrane asks for an attestation; if the key is unreachable the receipt is emitted unsigned. Trading
the guarantee for the attestation would be the wrong way round.

`canonical-prefix` is the first 8 bytes of `SHA256(content fields)`, 16 lowercase hex, and now
appears on every `membrane_receipt` log line alongside the whole receipt. It is the human-legible
handle — **not** the binding commitment. The signature is.

**It does not reach the counterparty**, and §3.4 has the arithmetic: 64 bits over eleven fields most
of which they hold or can guess is a preimage, not a handle. What reaches them is `dispute_token`, a
random UUID minted per decision and logged beside the receipt. Random rather than derived, so there
is nothing in it to enumerate toward; per decision rather than per session, because `session_token`
already names the session and cannot cite one round of a negotiation. Deliberately **not** a receipt
field: it is not signed content, and adding one would be a second format generation immediately
after V2 for a value no attestation needs. It is also not `decision_id` — that is signed content the
auditor reconciles, and keeping them separate means the counterparty holds nothing that is part of
an attestation.

### 3.8 ψ — what the rule set guarantees

**Implemented.** Every section above describes what the receipt *records*. None of them, until V2,
said what the rules being recorded actually **guarantee**. `ruleset_version` named a rule set;
nowhere in this document or the repo did anything state what holding that rule set buys you.

That is the difference between a certificate and a version string, and the gap was not academic.
Writing the missing statement down found a live bug.

**The bug**, under the pre-collapse per-gate strategy — the same inputs produce 112.52 in the run §4
walks through, and a different cent each run, because the jitter secret is process-lifetime random. With `floor_price = 100`, `min_profit_margin = 0.1`, and `internal_cost`
unset:

- `membrane/main.py` defaults `internal_cost` to `floor_price`, so cost = 100;
- the model proposes 92; `G2_FLOOR_VIOLATION` fails and `OutputGuard.evaluate` returns immediately,
  so **`G4_MARGIN_VIOLATION` never runs** — the gates short-circuit, by design (§3.4);
- the override substitutes `floor × 1.05 = 105.00` and emits it;
- realised margin is `(105 − 100) / 105 = 0.0476`, against a configured minimum of `0.10`.

The system emitted a price violating its own minimum-margin rule, on the default configuration — and
**the receipt for that decision was entirely valid.** `G2:fail` is truthfully recorded, the hashes
reconcile, the signature verifies. Nothing in the format was wrong. The gates judge **what the model
proposed**; nothing judged **what the Membrane substituted**. That gap opened the moment `override`
became a third outcome and had been open since.

The rule set's two substitute strategies are how the bug got through in the first place. `floor ×
1.05` and `floor / (1 − m)` were declared as alternatives and never differed in what they
guaranteed — the second is `≥` the first wherever the margin binds — so which one a gate named was
free choice, and `G2` happened to name the weaker. **Two strategies with indistinguishable
guarantees is a crack, and this is what came through it.** Collapsing them to one `safe_offer`
(§3.3) removes the choice; ψ removes the reliance on nobody making it wrongly again.

**ψ is checked on the emission, not on the proposal**, for exactly that reason. The value that leaves
is the only value that exists at the outbound boundary, and it is not always the value any gate saw.
It runs on **both** paths — `emit` and `override`. Checking only the override path would miss a
broken gate on the emit path; checking only the emit path would have missed this bug.

Its scope is the negotiation flow specifically. `trade` and `rwa_vault` return before the guard
block and are judged by no rule set at all, so `guard/negotiation`'s ψ does not and must not claim to
cover them — they need sibling families (§3.3).

**The margin clause is multiplicative, and that is not a style preference.**
`(price − cost) / price >= m` in binary floats on money is not decidable: at prices where the value
is exactly right the ratio evaluates to `0.09999999999999995` against `0.1`. Because ψ is
fail-closed, a 5e-17 artefact turns a correct decision into a hard refusal. `price × (1 − m) >= cost`
is algebraically identical for `price > 0`, has no division, and is exact over `Decimal`.

**The substitute rounds up, in `Decimal`, and depends on cost as well as floor.**

```
safe_offer(context) = ceil_to_cents( max(floor × 1.05, max(floor, internal_cost) / (1 − m)) × (1 + j) )
```

- `round(…, 2)` goes to the *nearest* cent, which for a margin substitute means toward breaching it
  half the time: at `floor = 100, m = 0.1` it emits `111.11` for a required `111.1111…`, and since
  `d/dp[(p − c)/p] > 0` the lower price is the lower margin. **A value that exists to be safe must
  round in the direction of the guarantee, never away from it.** `ROUND_CEILING` on `Decimal`, not
  `round()` on `float`.
- ψ's margin clause is stated against `internal_cost`, which arrives independently and which
  `membrane/main.py` merely *defaults* to `floor_price`. Where `internal_cost > floor`, no price
  derived from the floor alone satisfies ψ, and the guard would refuse its own safe offer.
- `m` comes from `_configured_margin()`, which clamps to `[0.0, 1.0)` and falls back to the default,
  so a missing or corrupt setting cannot produce a price below the floor. Non-finite inputs — NaN and
  ±∞ are legal over a protobuf `double` — are read as absent rather than propagated.
- Where **neither** floor nor cost yields a usable positive value there is no premise to price from,
  and `calculate_safe_price` raises `GuardUnavailable` rather than returning `0.0`. The prior
  behaviour returned a number that fails the guard's own `G1_PRICE_POSITIVE` and ψ's `price > 0`, and
  unlike an exception, one a caller could forward as a real counter-offer without learning it was
  never priced.

Both of the first two points were found by an audit that ran the first draft of this design against a
randomised grid: the original formula violated ψ in **115,888 of 200,000** cases, and after
correcting the rounding, ~4,000 violations remained where the price was exactly right and only the
binary-float ratio disagreed. The property test over `(floor, internal_cost, m, proposed_price,
request_id)` — either the emitted price satisfies ψ or the decision was refused — is the test that
would have caught the original bug, and the main reason ψ is executable rather than prose. **It is
`TestPsiHoldsOnEveryEmittedPrice` in `core/tests/test_membrane_postcondition.py`**, driven through
`inspect_outbound` rather than against the engine, so that "or the decision was refused" is actually
exercised. This document cited it for some time before it existed; what existed fixed the floor at
100, never varied the proposed price, and called `calculate_safe_price` directly.

**G4 and `PSI_MIN_MARGIN` state the same rule and now decide it the same way**, on Decimal and
against the same clamped margin. They did not: the gate read `(price − cost) / price >= m` in binary
floats against the raw `min_profit_margin`. Over a 1.6M-case scan, 9,444 admissible proposals failed
the gate while ψ held on the same numbers — each one substituted under a `MIN_MARGIN_VIOLATION`
receipt recording a violation that had not occurred. And because `min_profit_margin` is
env-configurable and `float("nan")` parses clean, while G3 checks presence rather than range, a
single typo made `margin < nan` false and opened the gate to everything, while ψ read the clamped
default and refused everything below `cost / (1 − m)` — a systematic `unavailable` outage from one
setting. §3.6 records why the receipt's `override_scope` check depends on these two agreeing.

**Everything fails closed.** A failed clause, a raising predicate, a guard that cannot be reached, an
unwired registry: each records `outcome = unavailable` with `outcome_gate = POSTCONDITION_VIOLATION`
and emits nothing. The unwired-registry case is the one this document asserted while the code did the
opposite: `inspect_outbound` returned before ψ when there was no registry, four screens below a
docstring calling an unwired Membrane "exactly the unreachable-guard case this fails closed on". With
no registry, a price of 1.0 against a floor of 1000 was emitted, marked `emit`, and its receipt
verified. The gates are skipped when there is nothing to ask; ψ is not. A post-condition nobody evaluated has not been established. The rejection that
goes out carries no price and no reason a counterparty can read — naming the clause would describe
the policy boundary to the party the policy holds at arm's length.

A ψ failure turning a working negotiation into a refusal is the accepted cost, and it is a real cost:
ψ is fail-closed, so every imprecision in it is paid for by a live negotiation. The mitigation is
that ψ is exactly the conjunction the gates already claim to enforce — if it fires, something is
broken — and `POSTCONDITION_VIOLATION` is loud and distinct.

One more premise defect, since it is the same shape: the `FAILURE_RECOVERY` path asked the guard for
a substitute priced from `floor_price` alone and then checked ψ against `floor_price` **and**
`internal_cost`. Two premise sets one line apart, so wherever `cost > floor × (1 − m)` the recovery
that exists to keep a broken decision alive emitted nothing — at floor 1000, cost 1200, m 0.1 it
produced 1111.11, `PSI_MIN_MARGIN` refused it, and the negotiation ended `unavailable`. It now asks
with the same context ψ is checked against.

One consequence worth naming: `membrane/main.py` still carries a hardcoded `floor_price * 1.05`
fallback at the two sites where the guard is unreachable. That is the formula the collapse removed,
and at `floor = 100, cost = 100, m = 0.1` it produces the exact 105.00 above. It survives because ψ
now catches what it produces — `PSI_MIN_MARGIN` fires on that value and nothing is emitted. The
fallback is no longer a hole; it is a value that gets refused.

## 4. Worked example

A real trace, taken from a local run rather than composed, and re-taken after the fixes below it.
The model proposes 92.00 EUR against a hidden floor of 100.00, with `internal_cost` unset (so it
defaults to the floor) and `min_profit_margin = 0.1`. `G2_FLOOR_VIOLATION` fires. The substitute is
`max(100 × 1.05, 100 / 0.9) = 111.1111…`, jittered for this session and rounded up to the cent:
**112.52**. ψ holds on it — `112.52 × 0.9 = 101.268 ≥ 100` — so it is emitted. (The cents move
between runs and only between runs: the jitter secret is process-lifetime random, §3.4.)

The eleven content fields — what the prefix is taken over, and what a signature would cover — in
order:

```
version           AURA-RECEIPT-V2-UNSIGNED
issued_at         2026-08-12T09:38:03Z
decision_id       dec-25f25f21-2d9d-…690047  ← the emission's Intent.identifier
request_id        req_5f2c                   ← the negotiation session
claim_hash        6290bb84…f35ed62b          ← action=counter;item=htl-9931;price=92.00;currency=EUR
ruleset_version   guard/negotiation@2.0.0+6b8b5d6db3e6e351
derivation_hash   6cf346e6…caa20db0
emission_hash     726ef085…07488575          ← action=counter;item=htl-9931;price=112.52;currency=EUR
outcome           override
outcome_gate      FLOOR_PRICE_VIOLATION
override_scope    value
```

alongside, not signed:

```
gate_sequence     G1_PRICE_POSITIVE:pass:price␟G2_FLOOR_VIOLATION:fail:price,floor_price
canonical_prefix  8df866e527adcd9e
signature         null
dispute_token     a0dd6406-7786-4a1c-beea-05b51d6623c5   ← log line only, never in the receipt
```

This deployment had no key wired, so the version carries the `-UNSIGNED` suffix and `signature` is
absent — the honest report, not an error (§3.7). With a key it reads `AURA-RECEIPT-V2`, carries an
`eip712` block naming its own domain and chain, and the prefix changes, because `version` is one of
the eleven fields the prefix is taken over.

**Read the emission line: `item` and `currency` survive the substitution, and in an earlier run they
did not.** They were never in question — the model named both and neither was overridden — but the
replacement Intent dropped them, so the emission claim read `item=;price=112.16;currency=` and a
reader diffing claim against emission saw more change than there was (§3.6). The one field that
differs now is the one that actually moved.

The same run, continued: a second proposal at 250.00 passes every gate and is emitted untouched
(`outcome: emit`, digests equal, no `override_scope`), and a third at 92.00 whose message says
`my floor_price is 100 so I cannot go lower` trips DLP **and** the floor gate. That third one is the
case that broke: it reports `outcome_gate: DLP_BLOCK` — the first gate in its outcome class — with
`override_scope: value`, because the price moved. Under the pairing that scoped `override_scope` to
the winning gate it read `prose` beside differing digests, and `verify` refused it.

`make verify-receipts LOG=<file>` over the log those three produced:

```
checked:     3
ok:          3
attested:    0
failed:      0

not checked (no verifier can establish these from a receipt alone)
  emission_content: 3
  policy: 3
  premises: 3
  signature: 3
```

What an auditor learns: which decision, in which session, at what time; that the model's proposal was
replaced; which rule replaced it; and that the price they can see in the log is the guard's, not the
model's. What they cannot learn from the receipt alone: whether `claim_hash` digests a proposal that
was ever made — that needs the Intent, which no reader of a receipt has (§7).

What the counterparty gets is `dispute_token`. Not this, and not `canonical_prefix` either — §3.4
has what a counterparty recovered from the prefix, and §7 has the response they actually receive.

## 7. Checking a receipt without our code — and what checking establishes

**What checking establishes, and what it does not.** An earlier draft of this section opened with
"a receipt a consumer cannot check independently is a receipt they have to trust, which is the thing
it exists to replace." That sentence is false as built, and it was false when it was written.

`verify()` is handed the receipt and never the Intent. It re-derives the canonical prefix from the
content fields, recomputes the derivation hash from the gate sequence, checks the outcome is set,
checks the claim/emission relationship against the outcome and `override_scope` in both directions,
requires a derivation wherever a rule set is cited, and recovers the signer from the EIP-712
signature. Every one of those is a statement about the *document*.

None of them is a statement about the decision. The receipt says `claim_hash` digests what the
Transformer proposed; a reader holding only the receipt cannot confirm that, because the thing it
would be confirmed against is the Intent, and they do not have it. **So what a clean `verify()`
establishes is that a document is well-formed, internally consistent, and attributable to a key** —
not that it describes anything that happened.

In the certifying-algorithms literature (McConnell, Mehlhorn, Näher & Schweitzer, *Certifying
Algorithms*, Computer Science Review 5(2), 2011) a checker is `C(x, y, w)` and §6.2 is explicit that
it must read the original, unmanipulated input. Ours reads `w` alone. Calling it a checker would be
an overclaim; it is a well-formedness verifier with an attestation step.

That is not left for a reader to discover. **Every receipt `verify()` returns carries
`emission_content` in `unverifiable`, signed or not, ok or not** — the function telling its own
caller, in machine-readable form, that it never saw the Intent and cannot vouch that `claim_hash`
digests anything real. It is joined there by `premises` and `policy` (never built — §3.1, §3.5), by
`signature` when the receipt is unsigned, and by `freshness` when `issued_at` is absent. A verifier
that answers "valid" while silently skipping a check teaches its consumer to rely on a guarantee
nobody made.

Closing it means `premise_hash`, which stays deferred for the reasons in §3.1 — and note that even
built, on our low-entropy premises it can only ever be a commitment opened to a party already
trusted with the floor, never a counterparty-verifiable field.

### Who actually reads one

Not the HTTP client. `/v1/negotiate` returns exactly this:

```json
{
  "session_token": "sess_…",
  "status": "countered",
  "valid_until": 1786…,
  "dispute_token": "a0dd6406-7786-4a1c-beea-05b51d6623c5",
  "data": { "proposed_price": 112.52, "message": "My counter-offer for this item is $112.52." }
}
```

**There is no `receipt` key.** Not the hashes, not `outcome_gate`, not the rule set, not the
derivation, not the signature — and not `version` or `canonical_prefix`, which an earlier V2 draft
kept. `NegotiateResponse` field 7 is `reserved`, so there is no renderer left to be careful with,
and the gateway's tests assert the absence against the whole serialised body rather than the top
level.

§1.1 is the audience reason and §3.4 is the arithmetic: `outcome_gate` names the rule that fired,
the rule set maps it to a substitute strategy, the price is already in the response, and the prefix
turned out to be a 64-bit preimage over fields the counterparty mostly holds. What they get instead
is `dispute_token` — random, per decision, resolvable only by the auditor. Be precise about what
that buys: it closes one-shot recovery of the model's proposed price and of which gate fired. It
does not close the channel; `proposed_price` is right there in the same object.

**The auditor's copy comes from the log.** `logger.info("membrane_receipt", …)` fires on every
decision and now carries the whole document rather than five scalar fields, with the prefix and the
`dispute_token` kept at the top level for correlation — the token is what turns a citation from a
counterparty into a decision an auditor can find. Nothing in `DecisionReceipt`, `DecisionDerivation` or
`ReceiptSignature` is a price or a premise value — every field is a digest, an identifier, an enum, a
timestamp or signature metadata — so logging it whole cannot leak.

`tools/verify_receipts.py`, wired as `make verify-receipts LOG=<path>`, reads that stream, runs
`verify()` over every `membrane_receipt` line, and prints checked / ok / attested / failed with
reasons, plus the tally of what could not be checked. It exits non-zero when any receipt failed, so
it can gate a job; an empty stream is not a failure, because nothing was decided. Malformed lines are
skipped rather than raised on — a truncated last line in a rotated file must not stop the audit of
everything before it.

**This is the consumer that was missing when step 6 was written off as unbuildable** (§6). The
verifier had existed since the receipt did and ran only in tests, because no receipt was persisted
anywhere. The log line makes the log the store, and the tool makes it read.

The gateway's two receipt renderers are gone with the response field. `receipt_to_json_full` never
had a production caller — the log line lives in core and carries betterproto's own `to_dict()` — and
`receipt_to_json` lost its only one. So did `NegotiationObservation.receipt`, the hop that carried
the receipt from the Connector toward a response that no longer has anywhere to put it; the field is
`reserved`. A transport step to a destination that no longer exists reads as load-bearing to the
next person.

### Recovering the signer

**Read `version` first.** `AURA-RECEIPT-V2-UNSIGNED` means the deployment had no attestation key
configured and `signature` is `null`. That is a legitimate configuration rather than a fault: the key
lives in `AURA_ATTESTATION__PRIVATE_KEY`, a deployment may run without one, and the decision is
emitted either way — losing a negotiation because a key was unreachable would trade the guarantee for
the attestation.

Until the attestation protein existed this sentence was false. Signing was gated on
`crypto.enabled`, a flag about payment locks, which was false in every deployed configuration — and
would not have signed anything had it been true, because no signing key was plumbed into the
deployment at all. `UNSIGNED` meant "crypto payments are off", not "no key configured". The key now
has its own section, its own protein, and no feature flag: the protein is registered when a key is
present and not otherwise.

Which address a deployment signs with is stated once at boot —
`attestation_signer_ready address=0x…` — and recorded in `docs/attestation-signers.md`. That file is
the durable half of the story: a signature recovers to an address, but only the record says the
address was ours. Verifying a past signature never needs the private key, so keys may rotate and be
lost without taking the corpus with them.

Everything else in the receipt is still checkable to the extent described
above, but nobody has vouched for it. Treating one as the other is the downgrade the two names exist
to prevent.

The signature covers a single string: the eleven content fields, joined by `\n`, in this exact
order.

```
version
issued_at
decision_id
request_id
claim_hash
ruleset_version
derivation.derivation_hash      ← empty string when derivation is null
emission_hash
outcome                         ← the name, e.g. "override" — not a number
outcome_gate
override_scope                  ← empty unless outcome is "override"
```

That string is the `content` member of an EIP-712 message, under a domain rebuilt from the receipt's
own `signature` block:

```python
payload = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
        ],
        "DecisionReceipt": [{"name": "content", "type": "string"}],
    },
    "domain": {
        "name": sig["domain"],           # AuraDecisionReceipt
        "version": sig["domain_version"],
        "chainId": sig["chain_id"],
    },
    "primaryType": "DecisionReceipt",
    "message": {"content": content},
}
recovered = Account.recover_message(encode_typed_data(full_message=payload), signature=sig["signature"])
assert recovered.lower() == sig["signer"].lower()
```

Note there is **no `verifyingContract`** — a receipt has no contract, and its absence is part of what
makes this domain structurally different from the one `TradeIntent` is signed under. Adding a zeroed
one produces a different domain separator and the recovery fails.

The recovered address is then resolved against the ERC-8004 identity registry to learn whether it is
ours. That step is the point of using the EVM key: the address means something because it is already
published, not because we assert it.

### What the fields tell you

- **`decision_id` / `request_id` / `issued_at`** — which decision, which session, when. Without them
  a receipt describes an equivalence class rather than a decision; `issued_at` is our clock, so it is
  freshness for someone who already trusts us (§1.1).
- **`claim_hash` ≠ `emission_hash`** — the Membrane substituted a value. The price that went out is
  the guard's, not the model's. Read it with `override_scope`: `value` means the substitution touched
  decidable content and the digests must differ; `prose` means it touched only free text and they
  must agree. Either combination inverted is a receipt describing something that did not happen, and
  `verify` reports both.
- **`ruleset_version`** — which rules judged it. The digest changes when the declared structure
  changes, and not when a predicate body does (§3.3); empty means no rule set was consulted, which is
  the case for Membrane-level refusals.
- **`outcome: "unavailable"`** — no verdict was established, and nothing was emitted. Not a rule
  judging against a decision; a judgment that did not happen (§3.6).
- **`derivation.gate_sequence`** — every gate that ran, in order, with its verdict, naming the
  premise *keys* each consulted. It never carries a value. That makes *this field* safe to publish;
  it does not make the counter-offer beside it safe (§3.4).
- **`canonical_prefix`** — a handle for correlating with our logs. Not a commitment; the signature
  is. Auditor-side only: it does not reach the counterparty, because it is invertible by enumeration
  (§3.4). The counterparty's handle is `dispute_token`, which is not a receipt field at all — it
  rides the log line beside the receipt, and the response beside the price.

And the field that is not there: nothing in the receipt lets you confirm that `claim_hash` digests a
proposal that was ever made. `unverifiable` says so on every receipt.

Our own implementation of all of this is `verify()` in `core/src/aura_hive/hive/membrane/receipt.py`.
It needs no key and no configuration, so it is usable directly by anyone who can import it — but the
format above is the contract, and a consumer reimplementing it owes us nothing.

## 5. Honest gaps

1. **No constraint graph.** §3.2 substitutes a flat canonical claim. We are building *attested
   deterministic guards*, not neuro-symbolic reasoning. The label matters for how we describe this
   externally.
2. **Premises are unattested.** VISION's `premise-hash` covers provenance — signed by whom, attested
   when. Our `floor_price` arrives in `Context.metadata` from the aggregator with no signature. Until
   pricing premises are signed at source, the receipt attests "the guard ran correctly on *these*
   inputs", not "these inputs were authentic."
3. **Most of our domain fails VISION's own gates 4–5.** Negotiation is time-varying and partly
   speculative. Receipts here attest *rule compliance*, not derivability of a price. Claiming the
   latter would be false advertising.
4. **Single verifier.** Co-located with inference, same trust boundary. The staked-verifier network
   (VISION ch. 7) is out of scope; §7.3 confirms migration would not invalidate receipts issued now.
5. **`verify()` is not a checker, and the receipt is a witness of the wrong class.** McConnell et al.
   require a witness predicate to satisfy *checkability* and *simplicity*, and §5.5 rules out by name
   the degenerate certificate that takes `w` as "the record of the computation of P on x" — because
   proving the witness property is then tantamount to proving P correct. `gate_sequence` plus
   `derivation_hash` is that example. Combined with the missing input (§7), the receipt attests
   well-formedness and attribution rather than correctness. ψ (§3.8) is the part of this we could fix
   without `premise_hash`: it states what the rule set guarantees, and it is executable, so the
   guarantee is checked on the value rather than asserted about the process.
6. **The receipt attests a decision, never a sequence.** Nothing chains one receipt to the previous
   one. `request_id` groups them because we say so, not because anything commits to it, so no receipt
   evidences that a round of a negotiation was not dropped, replayed or reordered.

## 6. Suggested build order

1. ~~`outcome` + `_record_intervention()` → typed field on `Intent`.~~ **DONE.**
   `DecisionOutcome` enum and `Intent.outcome` / `Intent.outcome_gate` in
   `proto/aura/core/v1/metabolism.proto`; stamped by `_stamp()` / `_settle()` in
   `membrane/main.py`; covered by `core/tests/test_membrane_outcome.py`. First-gate-wins
   **within an outcome class** is implemented and tested (§3.6); across classes the gate follows the
   outcome, or a psi failure downstream of a DLP block reports "unavailable because DLP". No crypto, no wire format yet.
2. ~~Extract `ruleset.yaml`; make `engine.py` its interpreter; derive `ruleset-version`.~~ **DONE**,
   and now at `2.0.0` — the per-gate substitute strategies collapsed into one and the post-condition
   was declared (§3.3, §3.8). `proteins/guard/ruleset.{yaml,py}`; the engine walks the declared gates
   and `SafetyViolation` carries the gate's code, replacing the substring match on the exception
   message. Covered by `core/tests/test_guard_{ruleset,gates}.py`. Caveat in §3.3: predicate bodies
   are still outside the digest.
3. ~~Emit `gate-sequence` + `derivation-hash`; add a replay test asserting byte-stability across
   runs.~~ **DONE.** `DecisionDerivation` on `Intent`; `OutputGuard.evaluate()` walks the gates once
   and returns the record, which travels on `SafetyViolation` for the failing path. Replay tests
   build a fresh Membrane, registry and guard per run, since anything surviving between them is
   state a verifier does not have. Covered by `core/tests/test_{guard,membrane}_derivation.py`.
4. Add `premise-hash` + salt, and split the policy stamp. **Deferred, and the reason changed.**
   Not merely "who holds the salt": our premises are low-entropy enough (a two-decimal floor over a
   bounded range — ~10⁷ candidates for the floor alone) that **anyone holding the salt can recover
   them by enumeration**. So the salt is exactly as secret as `floor_price`, and a premise hash can
   never be a counterparty-verifiable field — only a commitment we open to a party already trusted
   with the floor.

   That is a different threat from VISION's. §8.7.1 salts against *linkage* between receipts, on
   premises assumed high-entropy (a diagnosis, a customer identity), and records the salt in the
   policy stamp — which for us would accomplish nothing. Fifth divergence.

   If built, the right primitive is a **per-receipt random nonce stored with the receipt**, not a
   configured salt: no long-lived secret to rotate or leak in bulk, and opening is selective. That
   needs receipts persisted somewhere an auditor can read — the same gap that made the bee-keeper
   half of step 6 unbuildable. Worth answering first: **who opens it, and when?** Absent a concrete
   dispute or audit flow, this builds a ceremony nobody performs.

   Step 6 has since given the receipts a reader, so the storage half of that objection is weaker
   than it was. **The blocking half is untouched**: nobody has said who opens a commitment, in what
   dispute, against whom. Until that has an answer this stays deferred, and the reasoning above is
   the reasoning — not the absence of a place to put bytes.
5. ~~Sign with the identity key; wire `canonical-prefix` into logs and frontend.~~ **DONE for the
   backend.** EIP-712 with the existing EVM key under a domain of its own (§3.7); signing lives in
   the transaction protein, which owns the key, and verification in `membrane/receipt.py`, which
   needs none. `canonical_prefix` is on every `membrane_receipt` log line, beside the full receipt.

   **The frontend half is not done, and the audience decision changed what it would be.** The
   gateway puts no part of the receipt on the wire at all (§1.1, §3.4, §7), so a UI built for the
   negotiating counterparty has one opaque `dispute_token` to show and nothing else. A UI for an
   auditor is a different product with a different reader, and it is that one — if any — that this
   step now means.
6. ~~Typed `DecisionReceipt` proto message; bee-keeper verifies receipts in CI audit.~~ **DONE for
   the backend, by a different consumer than the one named.** `DecisionReceipt` exists and
   `Intent.receipt` replaces the three fields that accumulated on `Intent`. It carries
   `claim_hash` / `emission_hash`, so an override is visible as two differing digests rather than a
   claim to be trusted, plus the V2 binding fields and `canonical_prefix`. `membrane/receipt.py`
   mints and verifies; covered by `core/tests/test_receipt.py`.

   **The bee-keeper half was mis-specified and will not be built.** bee.Keeper audits *architecture*
   — it reads the codebase through an LLM and the VCS protein, and never sees an emitted `Intent`.
   There were no persisted receipts for it to verify either, so "verifies receipts in CI audit" had
   nothing to run against on both counts.

   **What was actually missing was a consumer, and it now exists.** The `membrane_receipt` log line
   carries the whole document, which makes the log the store; `tools/verify_receipts.py` and
   `make verify-receipts` run `verify()` over that stream and report totals, failures and the
   `unverifiable` tally, exiting non-zero when anything failed. No schema, no migration, no new
   responsibility on `PersistenceSkill`. Storing receipts properly is still open — see step 4 — but
   the receipt is no longer a document nobody reads.
7. ~~Declare ψ and check it on the emitted value.~~ **DONE**, and not in the original plan — it was
   added because writing down what the rule set guarantees found the bug in §3.8. `postcondition` in
   `ruleset.yaml` at `2.0.0`, clause predicates in `engine.py` cross-checked against the declaration
   in both directions, `check_postcondition` called by the Membrane on both the emit and override
   paths, `DECISION_OUTCOME_UNAVAILABLE` carrying the failure. Covered by
   `core/tests/test_guard_postcondition.py`, including the property test over
   `(floor, internal_cost, m, proposed_price, request_id)` that would have caught the original bug.

Steps 1–3, 6 and 7 pay for themselves regardless of whether the cryptographic layer ever lands.
Steps 4 and 5 each need an answer before any code is worth writing.
