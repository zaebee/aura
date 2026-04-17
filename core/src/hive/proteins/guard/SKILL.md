---
name: guard
description: Validate pricing decisions against safety guardrails before finalizing negotiations. Use when checking floor price compliance, minimum price enforcement, profit margin validation, deal pricing checks, discount approval, price guardrails, or triggering safe price fallbacks.
---

# Guard Skill: Price Safety Validation

Deterministic safety layer that enforces floor price and profit margin constraints on every negotiation action, regardless of LLM reasoning output.

## When to Use

- before finalizing any `counter` or `accept` action
- when a proposed price might breach `floor_price`
- when verifying `min_profit_margin` is maintained
- when you need a safe fallback price after a validation failure

## Capabilities

### `guard__validate_decision`

Check whether a proposed action passes all safety constraints (floor price and profit margin).

```
guard__validate_decision({
  decision: {
    action: "counter",
    price: 8500
  },
  context: {
    floor_price: 9000,
    internal_cost: 8000
  }
})
```

Returns on success:

```json
{ "success": true }
```

Returns on violation:

```json
{
  "success": false,
  "error": "Metabolic Leakage: Amount below floor price",
  "metadata": {
    "error_code": "FLOOR_PRICE_VIOLATION",
    "safe_price": "9450.0"
  }
}
```

`error_code` values:
- `FLOOR_PRICE_VIOLATION` — proposed price is below `floor_price`
- `MIN_MARGIN_VIOLATION` — margin `(price - internal_cost) / price` is below `min_profit_margin`
- `SAFETY_VIOLATION` — other safety constraint breached

`internal_cost` is required in `context` for margin checks. If safety settings are not configured the guard fails closed with a `SAFETY_VIOLATION`.

Use for:
- checking if a counter-offer respects the floor price
- verifying profit margin before accepting a deal

### `guard__get_safe_price`

Generate a deterministic safe counter-offer price.

```
guard__get_safe_price({
  context: {
    floor_price: 9000
  },
  reason: "margin"
})
```

Returns:

```json
{
  "success": true,
  "metadata": {
    "safe_price": "10000.0"
  }
}
```

`reason` controls the calculation:
- `"margin"` (or any string containing "margin") → `floor_price / (1 - min_profit_margin)`, e.g. 9000 / 0.9 = 10000
- anything else → `floor_price * 1.05`, e.g. 9000 * 1.05 = 9450

Use for:
- recovering after a `guard__validate_decision` failure
- replacing any price the LLM proposed that breached constraints
- providing a fallback when uncertain about deal safety

## Decision Flow

1. prepare your proposed action and price
2. call `guard__validate_decision` with the decision and context
3. if `success: true`, proceed with the action
4. if `success: false`, use `metadata.safe_price` from the response directly, or call `guard__get_safe_price` for a fresh calculation
5. use the safe price instead of the original proposal

### Example: Validation Failure and Recovery

The agent is selling. The LLM suggests countering at 8500, floor is 9000, internal cost is 8000.

1. call `guard__validate_decision({ decision: { action: "counter", price: 8500 }, context: { floor_price: 9000, internal_cost: 8000 } })`
2. result: `{ "success": false, "error": "Metabolic Leakage: Amount below floor price", "metadata": { "error_code": "FLOOR_PRICE_VIOLATION", "safe_price": "9450.0" } }`
3. use `9450.0` from `metadata.safe_price` as the counter-offer instead of 8500

Or call `guard__get_safe_price` explicitly:

1. call `guard__get_safe_price({ context: { floor_price: 9000 }, reason: "floor" })`
2. result: `{ "success": true, "metadata": { "safe_price": "9450.0" } }`
3. use `9450.0` as the counter-offer

## Rules

- never finalize a negotiation action without calling `guard__validate_decision` first
- if uncertain about a price, always call the guard rather than guessing
- the guard's decision is final and overrides any LLM reasoning that conflicts with it
- `guard__validate_decision` always returns a `safe_price` in `metadata` on failure — use it directly to avoid an extra round-trip
