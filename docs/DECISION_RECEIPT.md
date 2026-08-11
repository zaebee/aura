# Decision Receipt (AURA-RECEIPT-V1) — design sketch

Status: **draft / not implemented**. Adapted from VISION whitepaper v1.7.0 (Durov, 2026-05-05),
chapters 4–6. This document records where we follow that spec, and — more importantly — the three
places where our domain forces us to diverge from it.

## 1. What the receipt is for

Every `Intent` that leaves the Membrane carries a small, self-contained, signed artefact that lets a
third party confirm:

- the decision was produced under a **declared rule set at a declared version**;
- the **deterministic gates actually ran**, in order, and which one fired;
- the output **has not been altered** since the Membrane approved it;

…without seeing `floor_price`, `internal_cost`, or `min_profit_margin`. The receipt carries hashes,
not premises. That property is what makes it safe to hand to the counterparty we are negotiating
against.

Non-goal: proving the *Transformer* (LLM) reasoned well. The receipt attests the **Membrane's**
verdict over the LLM's proposal. That boundary is the whole point — see §5.

## 2. Where it is minted

`HiveMetabolism.execute()` step 4, inside `HiveMembrane.inspect_outbound()`, which is already our
verification boundary: it is the last deterministic checkpoint before `Connector.act()`.

```
signal → M(in) → A(perceive) → T(think) → M(out) ⇐ RECEIPT MINTED HERE → C(act) → G(pulse)
```

The receipt attaches to `Intent.metadata` under key `receipt` (text form) so it survives the
existing proto plumbing without a schema change on day one. A typed `DecisionReceipt` message in
`aura/core/v1/metabolism.proto` is the follow-up once the format stabilises.

## 3. Wire format

Ten lines, fixed order, ASCII, LF-terminated. Line order is part of canonicalisation; reordering
produces a different prefix and fails verification.

```
AURA-RECEIPT-V1
premise-hash:     <hex64>
claim-hash:       <hex64>
ruleset-version:  <family>@<major>.<minor>.<patch>+<hex16>
derivation-hash:  <hex64>
policy-stamp:     <field>=<value>[;<field>=<value>]*
emission-hash:    <hex64>
outcome:          emit | override | refuse
gate-sequence:    <gate-record>[\x1F<gate-record>]*
verifier:         <agent-id>@<keyfp-hex16> <sig-hex128>
canonical-prefix: <hex16>
```

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

**The salt is mandatory, not optional.** VISION §8.7.1 treats salting as a per-domain option, but
our premise set is low-entropy: `floor_price` is a two-decimal number over a bounded range, so an
unsalted `premise-hash` is brute-forceable in ~10⁶ hashes. A deployment-scoped salt (rotated per
epoch, its *commitment* published in the policy stamp) is required for the hidden-knowledge
invariant to survive contact with the receipt. Without it, publishing receipts would defeat the DLP
guard we already run in `inspect_outbound`.

Consequence, accepted: receipts become verifiable only by parties holding the salt (us, an auditor
under NDA, bee-keeper). The counterparty verifies everything *except* premise re-derivation. That is
still strictly more than they can check today.

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

### 3.3 `ruleset-version`

**Implemented.** `guard/negotiation@1.0.0+46cc0e38ca4f895c` — family, semver, and a digest over the
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

What the rule set does hold is the gate list, in evaluation order, each with the code it emits, the
premise keys it consumes, and the safe-price strategy that applies when it fires:

```yaml
family: guard/negotiation
version: 1.0.0
gates:
  - id: G1_PRICE_POSITIVE
    code: INVALID_PRICE
    consumes: [price]
    safe_price: floor_markup
  - id: G2_FLOOR_VIOLATION
    code: FLOOR_PRICE_VIOLATION
    consumes: [price, floor_price]
    safe_price: floor_markup
  - id: G3_SETTINGS_PRESENT      # fail-closed if misconfigured
    code: SETTINGS_MISSING
    consumes: []
    safe_price: margin
  - id: G4_MARGIN_VIOLATION
    code: MIN_MARGIN_VIOLATION
    consumes: [price, internal_cost]
    safe_price: margin
```

Two properties keep the version honest rather than decorative:

- **The declaration and the implementation cross-check, both ways.** `OutputGuard.__init__` calls
  `Ruleset.validate_against(gate_ids())` and refuses to construct on a mismatch. A declared gate with
  no predicate would never fire while the rule set advertises it; a predicate that is not declared
  runs outside anything a receipt can account for.
- **The shipped digest is pinned in a test.** Editing `ruleset.yaml` fails `test_guard_ruleset.py`
  until the pin is updated in the same commit — which is the moment to ask whether `version` should
  be bumped too.

The gate order shipped here is not a preference; it reproduces the order the if-chain applied, so
decisions already in flight keep the reason they were refused under. Note `G1_DLP_DISCLOSURE` and
`G2_ACTION_SCOPE` from the earlier sketch are absent: DLP lives in the Membrane rather than the
guard engine, and action scope is a precondition for judging at all rather than a gate that can
fail. Both would need a second family to be declared honestly.

**Still a partial content-address.** The digest covers the gate list, not the predicate bodies —
those are still Python. A change to what `_gate_margin_violation` computes does not move the digest,
so predicate edits require a manual `version` bump that nothing enforces. VISION §4.2.4 wants the
implementation content-addressed by the rule-set hash; we are not there.

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
  digest's job (§3.6). Keeping values out of this field is what stops the digest being a value
  oracle — you cannot probe it for the floor.
- The digest moves when the *steps* move: raising the floor so that `G2` fails where it passed
  changes it, but changing the floor while every gate still passes does not.

**Gates short-circuit, and the sequence ends where evaluation did.** A reader can see that the gates
after the failure were never consulted. This pairs with §4.3.5's reasoning behind `outcome_gate`
recording only the first failure: enumerating every gate that *would* have fired gives an adversary
an oracle over the policy configuration, and the boundary they would map is `floor_price`.

**Nothing derived is not an empty derivation.** When no declared gate ran — a decision outside the
guard's scope, an unwired Membrane, or one of the Membrane's own checks — the field is left unset
rather than carrying the hash of an empty string. Hashing nothing would assert a derivation that
never happened, and a verifier could reproduce that digest and conclude, falsely, that gates ran.

Note this covers the *guard's declared gates only*. KYC, trade-risk and DLP are Membrane-level checks
that no rule set declares, so they cannot be recorded as gates without inventing ids nothing versions
(§3.3). Those paths refuse with an `outcome_gate` and no derivation, which is the honest report.

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

### 3.6 `emission-hash` and `outcome`

`emission-hash = SHA256(canon(emitted Intent body))` — same field selection as `claim-hash`, applied
to the final Intent rather than the LLM's proposal. Comparing the two is exactly how a reader sees
that the Membrane intervened.

`outcome` is our third divergence. VISION has two terminal states, emit and refuse, and argues
forcefully that approximating instead of refusing is the failure mode of probabilistic systems. We
have a third state and we ship it deliberately: `_override_with_safe_offer()` **replaces** the LLM's
price with `calculate_safe_price()` and continues the negotiation. That is a product decision, not
an accident — dropping the conversation on every guard trip would be worse for the user.

The fix is not to remove the override. It is to **stop hiding it**:

| outcome | meaning | `claim-hash` vs `emission-hash` |
|---|---|---|
| `emit` | LLM proposal passed all gates unmodified | equal |
| `override` | a gate fired; Membrane substituted a deterministic safe value | differ |
| `refuse` | a gate fired; no emission (KYC failure, high-risk trade) | emission is the reason |

Today the override is recorded only in `_record_intervention()` telemetry and a `[MEMBRANE: …]`
suffix appended to free-text `reasoning`. Under this design it becomes a typed, signed,
counterparty-visible fact. That is the single highest-value change in this document and it is
independently useful even if the rest is never built.

`refuse` receipts carry a real `derivation-hash` (the hash of the refusal-reason record), not a
placeholder — a refusal is a closed derivation onto the refusal symbol (VISION §5.1.4).

### 3.7 `verifier` and `canonical-prefix`

Ed25519 over `canon(lines 2–9)`, signed with the agent's existing identity key — the same key
already used for wallet sanctification, which binds receipts to our ERC-8004 identity work. The
`verifier` value is `<agent-id>@<key-fingerprint-hex16>` followed by the 128-hex signature.

`canonical-prefix` is the first 8 bytes of `SHA256(canon(content fields))`, rendered as 16 lowercase
hex. It is the human-legible handle for logs, Telegram, and the frontend — **not** the binding
commitment. The signature is.

## 4. Worked example

LLM proposes 92.00 against a hidden floor of 100.00. Gate `G4_FLOOR_VIOLATION` fires; the Membrane
substitutes 105.00 (`floor × 1.05`).

```
AURA-RECEIPT-V1
premise-hash:     3f9a…c21e
claim-hash:       8b04…77da        ← action=counter;item=htl-9931;price=92.00;currency=EUR
ruleset-version:  guard/negotiation@1.0.0+9c1de4a70b3f5821
derivation-hash:  a17c…40f9
policy-stamp:     gates=6;jurisdiction=DEU;salt-commit=2b71c0aa19e4f003;thresholds=de44…;schema=1
emission-hash:    d5e1…0a3b        ← action=counter;item=htl-9931;price=105.00;currency=EUR
outcome:          override
gate-sequence:    G1_DLP_DISCLOSURE:pass:—\x1FG2_ACTION_SCOPE:pass:action\x1FG3_PRICE_POSITIVE:pass:price\x1FG4_FLOOR_VIOLATION:fail:price,floor_price
verifier:         aura-core-01@7d2f9b04ac11e630 4e91…（128 hex）
canonical-prefix: c0ffee1234abcd56
```

What the counterparty learns: a rule fired, at gate 4, consuming their offered price against a floor
they cannot see; the price they received is the Membrane's, not the model's; our thresholds were
committed beforehand. What they do not learn: the floor, the margin, the cost.

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

## 6. Suggested build order

1. ~~`outcome` + `_record_intervention()` → typed field on `Intent`.~~ **DONE.**
   `DecisionOutcome` enum and `Intent.outcome` / `Intent.outcome_gate` in
   `proto/aura/core/v1/metabolism.proto`; stamped by `_stamp()` / `_settle()` in
   `membrane/main.py`; covered by `core/tests/test_membrane_outcome.py`. First-gate-wins is
   implemented and tested. No crypto, no wire format yet.
2. ~~Extract `ruleset.yaml`; make `engine.py` its interpreter; derive `ruleset-version`.~~ **DONE.**
   `proteins/guard/ruleset.{yaml,py}`; the engine walks the declared gates and `SafetyViolation`
   carries the gate's code, replacing the substring match on the exception message. Covered by
   `core/tests/test_guard_{ruleset,gates}.py`. Caveat in §3.3: predicate bodies are still outside
   the digest.
3. ~~Emit `gate-sequence` + `derivation-hash`; add a replay test asserting byte-stability across
   runs.~~ **DONE.** `DecisionDerivation` on `Intent`; `OutputGuard.evaluate()` walks the gates once
   and returns the record, which travels on `SafetyViolation` for the failing path. Replay tests
   build a fresh Membrane, registry and guard per run, since anything surviving between them is
   state a verifier does not have. Covered by `core/tests/test_{guard,membrane}_derivation.py`.
4. Add hashes, salt, split policy stamp.
5. Sign with the identity key; wire `canonical-prefix` into logs and frontend.
6. Typed `DecisionReceipt` proto message; bee-keeper verifies receipts in CI audit.

Steps 1–3 are the ones that pay for themselves regardless of whether the cryptographic layer ever
lands.
