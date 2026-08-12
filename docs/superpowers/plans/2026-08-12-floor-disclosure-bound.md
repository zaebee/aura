# Floor Disclosure Bound Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docs/DECISION_RECEIPT.md` §3.4 state the bound that actually holds on the floor, instead of a bound that describes one channel and reads as a claim about the system.

**Architecture:** Documentation only. Two passages in §3.4 are amended and one follow-up issue is filed. No source file changes, no tests — there is no behaviour change to test, and adding one would assert that the document says something, which is what review is for.

**Tech Stack:** Markdown. `gh` for the issue.

**Spec:** `docs/superpowers/specs/2026-08-12-floor-disclosure-bound-design.md`

## Global Constraints

- **No source changes.** If this plan makes you want to edit a `.py` file, stop and re-read the spec: closing the channel was considered and is not possible, and the two rejected mitigations are named there with reasons.
- Facts to preserve exactly, all verified against the code before this plan was written:
  - `PSI_ABOVE_FLOOR` is `emitted_price >= floor_price` — `core/src/aura_hive/hive/proteins/guard/engine.py:359-360`.
  - ψ runs on every ACCEPT and COUNTER — `core/src/aura_hive/hive/membrane/main.py:920-923`.
  - The rules path accepts iff `bid >= floor_price` — `core/src/aura_hive/hive/transformer/main.py:107,118`.
  - Probe counts: 14 for a base of 100, **17 for 1,000**, 20 for 10,000, at cent precision.
- The existing 3% figure and the `base · ε / √(12N)` decay are **correct** and stay. They are being scoped to the counter-offer channel, not deleted.
- `make lint` must exit 0 before the commit. It lints Markdown only incidentally, but the repo runs it on everything and a trailing-whitespace hook will reject the commit otherwise.

---

### Task 1: Restate the bound in §3.4

**Files:**
- Modify: `docs/DECISION_RECEIPT.md` — the sentence at the top of the mitigation list ("**`ε` is a source constant…**"), and the closing list "So the claim is narrow, and it is not closure" at lines 445-456.

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This is prose.

- [ ] **Step 1: Scope the 3% sentence to its channel**

Find the paragraph beginning:

```
**`ε` is a source constant and therefore public, so the counterparty still learns the floor to within
3%.** That bound holds only because every floor-derived price is born in the guard, which applies the
markup and the jitter.
```

Replace only its first sentence, keeping the rest of the paragraph (the rules-strategy history and
the distinguishability note) exactly as it stands:

```markdown
**`ε` is a source constant and therefore public, so a counterparty reading counter-offers learns the
floor to within 3% per observation.** That is a bound on *this channel*, not on the floor — the
accept/reject channel below is exact, and dominates it. It holds only because every floor-derived
price is born in the guard, which applies the markup and the jitter.
```

- [ ] **Step 2: Add the oracle subsection**

Immediately **before** the line `So the claim is narrow, and it is not closure:` (line 445), insert:

```markdown
#### The channel none of this bounds

**An acceptance proves the bid was at or above the floor.** `PSI_ABOVE_FLOOR` is
`emitted_price >= floor_price` (`guard/engine.py`), and ψ runs on every ACCEPT and COUNTER
(`membrane/main.py`), so a decision to accept at price P cannot leave unless P ≥ floor. On every
path, by construction.

That makes acceptance an oracle, and it carries no jitter — nor could it, since noise on the
decision to accept means refusing sales above the floor. A counterparty who can bid and watch for
acceptance binary-searches:

| item base price | cent-precision values | probes |
|---|---|---|
| 100 | 10,000 | 14 |
| 1,000 | 100,000 | 17 |
| 10,000 | 1,000,000 | 20 |

`log₂(range ÷ precision)`, and the logarithm is the point: **widening the price range is not a
defence.** Doubling it costs the adversary one probe.

The oracle is one-sided, which changes what is learned rather than whether. Acceptance implies
`bid ≥ floor` always. Non-acceptance implies nothing definite on the LLM path — the model may
counter a bid above the floor for its own reasons — and is exact on the rules path, where
`bid < floor_price` counters and anything else accepts. So what a counterparty converges on is the
**infimum of accepted bids**: exactly the floor on the rules path, the floor or higher on the LLM
path. Either way it is the number they act on.

**This is not a defect and not fixable by trimming the response.** A threshold that decides
accept/reject is discoverable by probing the threshold — a property of having a reservation price,
not of this implementation. Note where it comes from: the safety guarantee is what creates the
proof. "Never emit below the floor" is precisely what makes an acceptance informative.

Three mitigations were considered and none is built. **Rate limiting per (counterparty, item)** is
the only one that changes anything: it closes nothing — nothing does — but stretches seventeen
probes over longer than a price stays current. **Stochastic refusal near the floor** would break the
proof by making acceptance non-deterministic, and is rejected: it costs revenue on honest bids and
destroys predictability for the buyers the system exists to serve, in order to slow an adversary who
can simply probe again. And **keying the jitter deterministically** — `HMAC(secret, item ‖
counterparty)` rather than on `request_id` — would close the averaging attack described above, since
a constant offset cannot be averaged away; it is recorded here because it is the obvious fix and it
addresses the channel that is not the problem. Against a repeat counterparty on one item it buys
almost nothing: there is no reason to average a hundred observations down to 0.09% when seventeen
probes give the cent.
```

- [ ] **Step 3: Correct the closing list**

Anchor on the text, not on a line number — Step 2 inserted a block above it, so every line below has
moved. Replace the bullet beginning `- **What it does not close:** \`proposed_price\` is still in the
response` and its three continuation lines with:

```markdown
- **What it does not close:** the floor. `proposed_price` is still in the response on every counter,
  so the 3% bound above still holds and still decays with `N` — and the accept/reject oracle is
  exact regardless, which is the bound that matters. Timing is a further residual: the override path
  makes extra registry round-trips, so a patient counterparty can distinguish an overridden counter
  from an ordinary one without reading a word of it.
```

- [ ] **Step 4: Check nothing else still claims 3% as the system's bound**

Run: `grep -n "within 3%\|to within 3\|3% of the base" docs/DECISION_RECEIPT.md`

Expected: only the sentence amended in Step 1, and the `base · ε / √(12N)` bullet in the mitigation
list, which describes the counter-offer channel and is correct. If §1.1 or §7 carries a similar
claim, amend it the same way — scope it to the channel rather than deleting it.

- [ ] **Step 5: Read the amended section end to end**

Not a mechanical check. Read §3.4 from "#### The leak this field closes, and the one it does not"
through the closing list and confirm it reads as one argument rather than as an old claim with a
correction stapled on. The section already distinguishes the derivation field from the channel
around it; the new subsection has to sit inside that structure, not restate it.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add docs/DECISION_RECEIPT.md
git commit -m "docs: name the channel that actually bounds the floor"
```

---

### Task 2: File the probe-cost follow-up

**Files:**
- None in the repository. This task produces a GitHub issue.

**Interfaces:**
- Consumes: the amended §3.4 from Task 1, which the issue cites.
- Produces: an issue number to reference if anyone picks the work up.

- [ ] **Step 1: Write the issue body**

Save to a scratch file and create it with `gh issue create --title "gateway: rate limit probes per (counterparty, item)" --body-file <path>`:

```markdown
`docs/DECISION_RECEIPT.md` §3.4 now states that acceptance is an exact proof that a bid was at or
above the floor, so a counterparty who can bid and watch for acceptance binary-searches the floor in
`log₂(range ÷ precision)` probes — 17 for a base of 1,000 at cent precision.

That channel cannot be closed. A threshold that decides accept/reject is discoverable by probing it,
and the safety guarantee is what creates the proof: ψ enforces `emitted_price >= floor_price`, so an
acceptance is informative by construction.

**Rate limiting is the only mitigation that changes the picture.** It does not close the channel —
it stretches the probes over longer than a price stays current, so the number an adversary recovers
is stale by the time they have it.

What this needs before it can be built:

- **How long a price is expected to stay valid.** Nobody has this number, and the limit is
  meaningless without it: a window that outlives the price is free, and one that undercuts honest
  repeat buyers costs sales.
- **A decision about honest repeat buyers.** Someone who negotiates the same item weekly is
  indistinguishable from a slow prober by this signal alone.
- **Where the counter lives.** The gateway already rate-limits; whether this is another dimension on
  that or a separate mechanism keyed on `(counterparty, item)` is the design question.

Explicitly rejected in the same section, so it does not get re-proposed: **stochastic refusal near
the floor.** It would break the proof by making acceptance non-deterministic, at the cost of revenue
on honest bids and of predictability for the buyers the system exists to serve — to slow an
adversary who can simply probe again.

Not urgent. Filed so the mitigation is recorded with its open questions rather than remembered as
"we should rate limit something".
```

- [ ] **Step 2: Note the issue number in the spec**

Append to the "Recorded, not built" section of
`docs/superpowers/specs/2026-08-12-floor-disclosure-bound-design.md`, under the **Probe cost**
paragraph:

```markdown
Filed as #<the number `gh issue create` printed in Step 1>.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-12-floor-disclosure-bound-design.md
git commit -m "docs(spec): link the probe-cost follow-up"
```
