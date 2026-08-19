---
sidebar_position: 1
---

# DNA Type Reference

:::info Auto-Generated
This page will be auto-generated from `proto/aura/dna/v1/dna.proto` using `protoc-gen-doc`.
:::

## Core Types

### Signal
The root message type for all user requests.

```protobuf
message Signal {
  Context context = 1;
  Intent intent = 2;
}
```

### Context
Metadata about the request session.

```protobuf
message Context {
  string session_id = 1;
  string user_id = 2;
  map<string, string> metadata = 3;
}
```

### Intent
The user's intended action and parameters.

```protobuf
message Intent {
  string action = 1;
  google.protobuf.Struct params = 2;
}
```

## Next Steps

Run `bun run gen:proto-docs` to generate complete API reference from Protobuf files.
