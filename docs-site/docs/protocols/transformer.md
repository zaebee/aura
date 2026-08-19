---
sidebar_position: 3
---

# T (Transformer) Protocol

The **Transformer** protocol implements core business logic and makes decisions.

## Purpose

Transform enriched signals into decisions:
- Analyze aggregated context
- Apply business rules
- Make state transitions
- Compute outcomes

## Key Principles

1. **Pure**: Deterministic given same inputs
2. **Focused**: Only business logic, no I/O
3. **Explicit**: Clear decision tree
4. **Testable**: Easily unit tested

## Implementation Example

```python
def transformer(self, enriched: EnrichedSignal) -> Decision:
    bid = enriched.signal.intent.params["bid_amount"]
    item = enriched.item

    if bid >= item.asking_price:
        return Decision(outcome="accept")

    elif bid >= item.floor_price * 0.9:
        return Decision(
            outcome="counter",
            counter_amount=item.floor_price * 0.95
        )

    else:
        return Decision(outcome="reject")
```

## Best Practices

- Keep it pure (no side effects)
- Extract rules into functions
- Use pattern matching for decision trees
- Document business rules inline
