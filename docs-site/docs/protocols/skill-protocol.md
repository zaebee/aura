---
sidebar_position: 7
---

# Skill Protocol

Skills are external capabilities invoked by the Generator protocol.

## What is a Skill?

A **Skill** is an external tool or API that extends Protein capabilities:
- Payment processing (Stripe)
- Email sending (SendGrid)
- Search indexing (Algolia)
- Custom integrations

## Invocation Pattern

```python
async def invoke_skill(
    self,
    skill_name: str,
    params: dict
) -> SkillResult:
    # Publish skill request
    response = await self.nats.request(
        f"hive.skill.{skill_name}.invoke",
        SkillRequest(params=params).to_bytes(),
        timeout=10.0
    )
    return SkillResult.from_bytes(response.data)
```

## Skill Registration

Skills register themselves on startup:

```python
await nats.subscribe(
    "hive.skill.stripe.invoke",
    handler=stripe_skill_handler
)
```

## Best Practices

- Use timeouts
- Handle skill failures gracefully
- Log skill invocations
- Monitor skill performance
