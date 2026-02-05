---
sidebar_position: 4
---

# C (Connector) Protocol

The **Connector** protocol routes responses to their destinations.

## Purpose

Send responses to:
- API gateway (HTTP response)
- WebSocket connections
- Email/SMS notifications
- External webhooks

## Implementation Example

```python
async def connector(self, response: Response, signal: Signal):
    # Send HTTP response
    await self.nats.publish(
        f"hive.api.response.{signal.context.request_id}",
        response.to_bytes()
    )

    # Send notification
    if response.outcome == "counter":
        await self.send_notification(
            signal.context.user_id,
            f"Counter offer: ${response.counter_amount}"
        )
```

## Best Practices

- Fire-and-forget (don't wait for acks)
- Use circuit breakers for external systems
- Log routing decisions
- Handle delivery failures gracefully
