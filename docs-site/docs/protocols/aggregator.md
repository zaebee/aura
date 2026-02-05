---
sidebar_position: 2
---

# A (Aggregator) Protocol

The **Aggregator** protocol gathers all context and data needed for decision-making.

## Purpose

Fetch related data from:
- Databases (PostgreSQL)
- External APIs
- Cache layers (Redis, NATS KV)
- Other proteins (via NATS request-reply)

## Key Principles

1. **Read-only**: Never mutate state
2. **Comprehensive**: Gather everything needed for T (Transformer)
3. **Efficient**: Use async I/O, batch queries, caching
4. **Fault-tolerant**: Handle missing data gracefully

## Implementation Example

```python
async def aggregator(self, signal: Signal) -> EnrichedSignal:
    # Parallel fetches
    item, user, history = await asyncio.gather(
        self.db.items.get(signal.intent.params["item_id"]),
        self.db.users.get(signal.context.user_id),
        self.db.negotiations.get_history(signal.context.user_id)
    )

    return EnrichedSignal(
        signal=signal,
        item=item,
        user=user,
        history=history
    )
```

## Best Practices

- Use parallel fetches (`asyncio.gather`)
- Cache frequently accessed data
- Set timeouts on external calls
- Return partial data if some sources fail
