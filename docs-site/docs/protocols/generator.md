---
sidebar_position: 5
---

# G (Generator) Protocol

The **Generator** protocol emits events and triggers side effects.

## Purpose

Generate:
- Domain events (for event sourcing)
- Analytics events
- Skill invocations
- Search index updates

## Implementation Example

```python
async def generator(self, response: Response, signal: Signal):
    # Emit domain event
    await self.nats.publish(
        "hive.events.bid.placed",
        BidPlacedEvent(
            item_id=signal.intent.params["item_id"],
            user_id=signal.context.user_id,
            outcome=response.outcome
        ).to_bytes()
    )

    # Track analytics
    await self.analytics.track(
        "bid_placed",
        {"outcome": response.outcome}
    )

    # Invoke skill if needed
    if response.outcome == "accept":
        await self.invoke_skill("update_search_index", {...})
```

## Best Practices

- Emit events asynchronously
- Use structured event schemas (Protobuf)
- Include correlation IDs for tracing
- Don't block on external skills
