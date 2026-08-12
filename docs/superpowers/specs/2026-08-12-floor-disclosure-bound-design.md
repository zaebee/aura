# The floor disclosure bound, restated — design

**Status:** approved, not implemented
**Date:** 2026-08-12
**Amends:** `docs/DECISION_RECEIPT.md` §3.4
**Follows:** `2026-08-12-receipt-durability-design.md`

## Why

§3.4 currently says the counterparty "still learns the floor to within 3%", bounded by the
per-session jitter on substitute prices. That sentence is true about one channel and false as a
statement about the system.

**Acceptance is an exact proof that the bid was at or above the floor.** `PSI_ABOVE_FLOOR` is
`emitted_price >= floor_price` (`guard/engine.py:359-360`), and ψ runs on every ACCEPT and COUNTER
(`membrane/main.py:920-923`). So a decision to accept at price P cannot be emitted unless P ≥ floor,
on every path, by construction.

A counterparty who can bid and observe acceptance therefore binary-searches the floor. Jitter does
nothing about this: it lives in the counter-offer, and the accept/reject channel carries no noise at
all.

The work is to say so. **No code changes.**

## What this is not

Not a defect, and not fixable by removing fields from the response. A threshold that decides
accept/reject is discoverable by probing the threshold; that is a property of having a reservation
price, not of this implementation. It is worth noticing that the safety guarantee is what creates
the proof: "never emit below the floor" is exactly what makes an acceptance informative.

Not a jitter change either. Deterministic keying — `HMAC(secret, item ‖ counterparty)` instead of
`HMAC(secret, request_id)` — would close the averaging attack the current text describes, and was
the obvious fix until the oracle turned up. Against a repeat counterparty on one item it buys almost
nothing: why average a hundred observations down to 0.09% when seventeen probes give the cent.

## The claim, restated

### The oracle is one-sided, and the asymmetry matters

- **Acceptance ⟹ bid ≥ floor.** Always, every path. ψ enforces it on the emitted value.
- **Non-acceptance ⟹ nothing definite**, on the LLM path: the model may counter a bid above the
  floor for its own reasons. On the rules path it is exact — `bid < floor_price` counters and
  anything else accepts (`transformer/main.py:107,118`).

So what a counterparty converges on is **the infimum of accepted bids**: exactly the floor on the
rules path, the floor or higher on the LLM path. That is the operative number for them either way —
arguably more useful than the floor itself.

### The probe count is logarithmic

`log₂(range ÷ precision)`, computed:

| item base price | cent-precision values | probes |
|---|---|---|
| 100 | 10,000 | 14 |
| 1,000 | 100,000 | 17 |
| 10,000 | 1,000,000 | 20 |

The logarithm is the point: **widening the price range is not a defence.** Doubling it costs the
adversary one probe.

### Two channels, two bounds

| channel | what it carries | bound |
|---|---|---|
| counter-offer (`proposed_price`) | a floor-derived price with markup and jitter | 3% per observation, decaying as `base·ε/√(12N)` |
| accept / reject | ψ's guarantee, unjittered | exact, in `log₂(range ÷ precision)` probes |

The 3% figure stays in the document, scoped to the channel it describes. It stops being the
system's bound.

## What the document must stop implying

That trimming the response protects the floor. §7's removal of the receipt closed one-shot recovery
of the *model's proposed price* and *which gate fired* — a real and different thing, correctly
described there. It never touched the floor, and §3.4's 3% sentence read as though the two were
the same defence.

## Recorded, not built

**Probe cost.** Rate limiting per (counterparty, item) is the only mechanism that changes the
picture: it does not close the channel — nothing does — but it stretches seventeen probes over
longer than the price stays current. That is its own piece of work in the gateway, and it needs a
number nobody has yet: how long a price is expected to remain valid.

**Stochastic refusal near the floor** would break the proof by making acceptance non-deterministic.
Rejected: it costs revenue on honest bids and destroys predictability for the buyers the system
exists to serve, to slow an adversary who can simply probe more.

## Scope

One passage in `docs/DECISION_RECEIPT.md` §3.4 — the "leak this field closes, and the one it does
not" subsection — plus a follow-up issue for probe cost. No source file changes, no tests, because
there is no behaviour change to test.

## Risks

**Writing down an attack.** The document is internal and the arithmetic is elementary; a
counterparty motivated to probe does not need our notes to think of bidding lower. The cost of not
writing it down is an operator who reads "within 3%" and prices as though the floor were protected.

**The bound looks worse than before.** It is not — it was always this, and the previous sentence
measured the wrong channel. Anyone comparing revisions should read this as a correction to the
claim, not a regression in the system.
