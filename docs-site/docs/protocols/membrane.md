---
sidebar_position: 6
---

# M (Membrane) Protocol

The **Membrane** protocol enforces sovereignty and validation at input/output boundaries.

## Purpose

### M(in) - Input Validation
- Validate signal schema
- Check permissions
- Enforce rate limits
- Verify business constraints

### M(out) - Output Validation
- Validate response schema
- Apply output transformations
- Enforce post-conditions
- Sanitize sensitive data

## Implementation Example

```python
def membrane_in(self, signal: Signal) -> Signal:
    # Validate bid amount
    bid = signal.intent.params["bid_amount"]
    if bid < 1.0:
        raise ValueError("Bid must be at least $1")

    # Check rate limit
    if not self.rate_limiter.allow(signal.context.user_id):
        raise ValueError("Rate limit exceeded")

    return signal

def membrane_out(self, decision: Decision, signal: Signal) -> Response:
    # Enforce minimum counter increment
    if decision.outcome == "counter":
        min_counter = signal.intent.params["bid_amount"] * 1.05
        if decision.counter_amount < min_counter:
            decision.counter_amount = min_counter

    return Response(...)
```

## Best Practices

- Fail fast on invalid input
- Use typed exceptions
- Log validation failures
- Apply defense-in-depth
