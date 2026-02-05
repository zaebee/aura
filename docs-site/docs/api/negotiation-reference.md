---
sidebar_position: 2
---

# Negotiation API Reference

:::info Auto-Generated
This page will be auto-generated from `proto/aura/negotiation/v1/negotiation.proto`.
:::

## Negotiation Types

### NegotiateRequest

```protobuf
message NegotiateRequest {
  string item_id = 1;
  double bid_amount = 2;
  string user_id = 3;
}
```

### NegotiateResponse

```protobuf
message NegotiateResponse {
  string outcome = 1;  // accept | counter | reject | ui_required
  double counter_amount = 2;
  string message = 3;
}
```

## Next Steps

Run `bun run gen:proto-docs` to generate complete API reference.
