---
name: guard
description: Validate pricing decisions against safety guardrails before finalizing negotiations. Use when checking floor price compliance, minimum price enforcement, profit margin validation, deal pricing checks, detecting inconsistent offer sequences, discount approval, price guardrails, or triggering safe price fallbacks.
---

# Guard Skill: Price Safety Validation

Deterministic safety layer that enforces floor price and profit margin constraints on every negotiation action, regardless of LLM reasoning output.

## When to Use

- before finalizing any `counter` or `accept` action
- when a proposed price might breach `floor_price`
- when verifying `min_profit_margin` is maintained
- when the current offer contradicts the previous turn's direction (inconsistent pricing sequence)
- when you need a safe fallback price after a validation failure

## Capabilities

### `guard__validate_safety`

Check whether a proposed price passes all safety constraints.

```
guard__validate_safety({
  proposed_price: 8500,
  floor_price: 9000,
  min_profit_margin: 0.10,
  last_offer: 9500,
  role: "seller"
})
```

Returns:

```json
{
  "safe": false,
  "violations": ["below_floor_price", "inconsistent_sequence"],
  "details": "proposed 8500 is below floor 9000 and below last seller offer 9500"
}
```

Use for:
- checking if a counter-offer respects the floor price
- verifying profit margin before accepting a deal
- detecting when the current offer moves against the agent's own negotiation direction

### `guard__get_safe_price`

Generate a deterministic safe counter-offer when validation fails.

```
guard__get_safe_price({
  floor_price: 9000,
  min_profit_margin: 0.10,
  last_offer: 9500,
  role: "seller"
})
```

Returns:

```json
{
  "safe_price": 9200,
  "reasoning": "midpoint between floor 9000 and last offer 9500, maintaining margin"
}
```

Use for:
- recovering after a `guard__validate_safety` failure
- replacing any price the LLM proposed that breached constraints
- providing a fallback when uncertain about deal safety

## Decision Flow

1. prepare your proposed price or action
2. call `guard__validate_safety` with proposed price, floor, margin, last offer, and role
3. if `safe: true`, proceed with the action
4. if `safe: false`, call `guard__get_safe_price` to get a corrected value
5. use the corrected value instead of the original proposal

### Example: Validation Failure and Recovery

The agent is selling and last offered 9500. The LLM suggests countering at 8500.

1. call `guard__validate_safety({ proposed_price: 8500, floor_price: 9000, min_profit_margin: 0.10, last_offer: 9500, role: "seller" })`
2. result: `{ "safe": false, "violations": ["below_floor_price", "inconsistent_sequence"] }`
3. call `guard__get_safe_price({ floor_price: 9000, min_profit_margin: 0.10, last_offer: 9500, role: "seller" })`
4. result: `{ "safe_price": 9200 }`
5. use 9200 as the counter-offer instead of 8500

## Rules

- never finalize a negotiation action without calling `guard__validate_safety` first
- if uncertain about a price, always call the guard rather than guessing
- treat every inconsistent pricing sequence as a critical event requiring `guard__get_safe_price`
- the guard's decision is final and overrides any LLM reasoning that conflicts with it
