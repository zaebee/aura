---
sidebar_position: 3
---

# Binary Bloodstream

The **Binary Bloodstream** is the message transport layer connecting all Proteins in the Hive. Built on NATS JetStream, it provides reliable, ordered delivery of typed messages encoded in Protobuf.

## Why NATS?

- **Simple**: No Kafka/Zookeeper complexity
- **Fast**: Written in Go, ~10M msgs/sec
- **Reliable**: JetStream adds persistence and exactly-once delivery
- **Flexible**: Pub/sub, request-reply, queue groups, KV store
- **Lightweight**: Single binary, low memory footprint

## Subject Hierarchy

Messages are routed via hierarchical subjects:

```
hive.protein.<protein_name>.<action>.<direction>

Examples:
- hive.protein.negotiate.request       (Negotiation request)
- hive.protein.negotiate.response      (Negotiation response)
- hive.protein.nlu.classify            (NLU classification)
- hive.protein.skill.invoke            (Skill invocation)
- hive.events.bid.placed               (Domain event)
- hive.events.payment.completed        (Domain event)
```

## Message Types

### 1. Request-Reply
Synchronous communication (with timeout):

**Python (Backend)**:
```python
response = await nc.request(
    "hive.protein.negotiate.request",
    signal.to_bytes(),
    timeout=5.0
)
negotiation_response = NegotiateResponse.from_bytes(response.data)
```

**TypeScript (Frontend via API)**:
```typescript
const response = await fetch('/api/negotiate', {
  method: 'POST',
  body: JSON.stringify(signal),
});
// API gateway translates HTTP → NATS → HTTP
```

### 2. Publish-Subscribe
Async event broadcasting:

**Publisher**:
```python
await nc.publish(
    "hive.events.bid.placed",
    BidPlacedEvent(...).to_bytes()
)
```

**Subscribers** (multiple can listen):
```python
# Analytics subscriber
async for msg in nc.subscribe("hive.events.bid.placed"):
    event = BidPlacedEvent.from_bytes(msg.data)
    await analytics.track(event)

# Notification subscriber
async for msg in nc.subscribe("hive.events.bid.placed"):
    event = BidPlacedEvent.from_bytes(msg.data)
    await send_notification(event.user_id, event)
```

### 3. Queue Groups
Load-balanced work distribution:

```python
# Worker 1, 2, 3 all subscribe with same queue name
# NATS ensures only one worker processes each message
async for msg in nc.subscribe(
    "hive.protein.negotiate.request",
    queue="negotiation-workers"
):
    await process_negotiation(msg)
```

## JetStream Streams

Persistent event storage with replay:

```yaml
stream:
  name: HIVE_EVENTS
  subjects:
    - hive.events.>
  retention: limits
  max_age: 30d
  storage: file
  replicas: 3
```

**Benefits**:
- Replay events for debugging
- Build derived views
- Audit trail
- Disaster recovery

## KV Store

Distributed key-value storage:

```python
# Store user session state
kv = await js.create_key_value(bucket="sessions")
await kv.put(f"session:{user_id}", session_data.to_bytes())

# Retrieve later
entry = await kv.get(f"session:{user_id}")
session = Session.from_bytes(entry.value)
```

## Message Encoding

All messages use **Protobuf** for:
- Type safety
- Schema evolution (backward/forward compatibility)
- Compact binary format
- Cross-language support

**Example message**:
```protobuf
message Signal {
  Context context = 1;
  Intent intent = 2;
}

message Context {
  string session_id = 1;
  string user_id = 2;
  map<string, string> metadata = 3;
}

message Intent {
  string action = 1;
  google.protobuf.Struct params = 2;
}
```

## Error Handling

### Timeouts
```python
try:
    response = await nc.request(subject, data, timeout=5.0)
except TimeoutError:
    # Handle timeout (no response within 5 seconds)
    return default_response()
```

### Dead Letter Queue
```python
# Failed messages go to dead letter subject
await nc.publish(
    "hive.dlq.negotiate",
    failed_message,
    headers={"error": str(exception)}
)
```

### Circuit Breaker
```python
if failure_rate > 0.5:
    # Stop sending requests, return cached/default response
    return circuit_open_response()
```

## Monitoring

### NATS Metrics
- Message rate (msgs/sec)
- Consumer lag
- Connection count
- Memory usage

### Custom Metrics
```python
# Track message processing time
with timer("negotiate.process_time"):
    response = await process_negotiation(signal)

# Track success/error rates
counter("negotiate.success").inc()
counter("negotiate.error", labels={"error_type": type(e).__name__}).inc()
```

## Deployment

### Local Development
```bash
# Run NATS with JetStream enabled
docker run -p 4222:4222 nats:latest -js
```

### Production (Railway)
```yaml
services:
  nats:
    image: nats:latest
    command: "-js -m 8222"
    ports:
      - "4222:4222"
      - "8222:8222"  # Monitoring
    volumes:
      - nats-data:/data
```

## Best Practices

1. **Use typed messages**: Always encode with Protobuf
2. **Set timeouts**: Prevent hanging requests
3. **Handle errors**: Use dead letter queues
4. **Monitor lag**: Watch consumer lag metrics
5. **Batch events**: Group related events for efficiency
6. **Version subjects**: Include version in subject (e.g., `v1.negotiate`)

## Next Steps

- Learn about [Proteins](../protocols/atcg-overview)
- See [event flow diagrams](../visual/pipelines/nats-events)
- Try the [interactive simulator](../interactive/negotiation-simulator)
