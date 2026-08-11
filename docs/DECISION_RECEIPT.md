# Decision Receipt (AURA-RECEIPT-V1) — design sketch

Status: **steps 1, 2, 3, 5 and 6 built; step 4 deferred.** Adapted from VISION whitepaper v1.7.0
(Durov, 2026-05-05), chapters 4–6. This document records where we follow that spec and — more
importantly — the five places where our domain forces us to diverge from it. Sections marked
*Implemented* describe code; the rest is still design.

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

The receipt is `Intent.receipt`, a typed `DecisionReceipt` in
`aura/core/v1/metabolism.proto`. It is minted after the verdict is settled and signed by the
transaction protein, which owns the key; a receipt that cannot be signed is emitted unsigned rather
than costing the decision.

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

**Implemented.** The override used to be recorded only in `_record_intervention()` telemetry and a
`[MEMBRANE: …]` suffix on free-text `reasoning`; it is now a typed, counterparty-visible fact —
though not yet a signed one.

Two limits worth stating rather than discovering later:

- **A prose-only override shows equal hashes.** The DLP gate rewrites the message and nothing else,
  and prose is deliberately outside the claim (§3.2). So a DLP-only override is visible through
  `outcome` but not through the digests. Bringing prose into the hash would cost determinism on
  every decision to catch this one case, so `verify` special-cases the gate instead: an override
  under a non-prose gate whose hashes agree is a receipt describing something that did not happen,
  and is reported as a failure.
- **`refuse` receipts carry no derivation.** VISION §5.1.4 wants a real digest there, since a
  refusal is a closed derivation onto the refusal symbol. Ours are Membrane-level checks (KYC,
  trade risk) that no rule set declares, so there are no gate ids to record (§3.3). They carry an
  `outcome_gate` and an empty derivation, which is honest but is a gap against the spec.

### 3.7 `signature` and `canonical-prefix`

**Implemented.** EIP-712 over the receipt's content fields, signed with the agent's existing
**EVM key** — not the Ed25519 scheme this document first sketched.

The reason is key distribution, not convenience. **A signature under a key nobody can attribute is
decoration.** Signing is the easy half; giving a counterparty a way to learn that the key is ours is
the hard one, and the EVM identity already has an answer — the recovered address resolves against
the ERC-8004 identity registry. A fresh Ed25519 key would have had no such story, and inventing one
is a larger piece of work than all of step 5.

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

**Two formats, not one format with a flag.** `AURA-RECEIPT-V1` is signed; `AURA-RECEIPT-V0-UNSIGNED`
is what a deployment with no key configured honestly produces. Separate names so a consumer written
against the signed format cannot be satisfied by a downgrade, and `verify` refuses a version it does
not recognise rather than best-effort checking it. `VerificationResult.attested` is true only when a
signature was present *and* recovered to the signer the receipt claims.

**Signing never costs a decision.** The decision is already made and already safe by the time the
Membrane asks for an attestation; if the key is unreachable the receipt is emitted unsigned. Trading
the guarantee for the attestation would be the wrong way round.

`canonical-prefix` is the first 8 bytes of `SHA256(content fields)`, 16 lowercase hex, and now
appears on every `membrane_receipt` log line alongside the outcome, gate and rule set. It is the
human-legible handle — **not** the binding commitment. The signature is.

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
5. ~~Sign with the identity key; wire `canonical-prefix` into logs and frontend.~~ **DONE for the
   backend.** EIP-712 with the existing EVM key under a domain of its own (§3.7); signing lives in
   the transaction protein, which owns the key, and verification in `membrane/receipt.py`, which
   needs none. `canonical_prefix` is on every `membrane_receipt` log line.

   **The frontend half is not done.** It needs the receipt on the wire past the gateway and a place
   in the UI to show it, which is its own piece of work rather than a line of this one.
6. ~~Typed `DecisionReceipt` proto message; bee-keeper verifies receipts in CI audit.~~
   **PARTLY DONE.** `DecisionReceipt` exists and `Intent.receipt` replaces the three fields that
   accumulated on `Intent` (7, 8 and 9 are reserved). It adds `claim_hash` / `emission_hash`, so an
   override is visible as two differing digests rather than a claim to be trusted, and
   `canonical_prefix`. `membrane/receipt.py` mints and verifies; covered by
   `core/tests/test_receipt.py`.

   **The bee-keeper half was mis-specified and is not built.** bee.Keeper audits *architecture* —
   it reads the codebase through an LLM and the VCS protein, and never sees an emitted `Intent`.
   There are no persisted receipts in CI for it to verify, so "verifies receipts in CI audit" had
   nothing to run against. Receipt checking is a library function (`verify`) exercised by tests
   instead. Wiring it into a real audit needs decisions persisted somewhere an auditor can read,
   which is its own piece of work and not obviously worth doing before the receipts are signed.

Steps 1–3 and 6 pay for themselves regardless of whether the cryptographic layer ever lands. Steps
4 and 5 each need an answer before any code is worth writing.
