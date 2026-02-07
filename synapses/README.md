# Synapses

**World Interfaces for the Bio-Digital Architecture**

Synapses are the "Sensory-Motor" interfaces of the Aura Platform. They handle the "Synaptic Gap" between the external world (Telegram, MCP, etc.) and the internal Metabolism (Hive Core).

## Anatomy of a Synapse

Every synapse follows a strict standardized structure:

- `manifest.yaml`: Metadata, required NATS subjects, and capabilities.
- `receptor.py`: Afferent logic (External World -> `metabolism.execute()`).
- `effector.py`: Efferent logic (NATS Bloodstream -> External World).
- `translator.py`: Data mapping logic (External JSON/Payload <-> Internal Protobuf/Types).

## Receptor-Effector Pattern

1. **The Receptor (Afferent)**: Receives an external event, translates it into an internal `Signal`, and triggers the `MetabolicLoop`.
2. **The Effector (Efferent)**: Listens to the `Pulse` (NATS Bloodstream), translates internal events into user-friendly messages, and sends them back to the external world.

## Available Synapses

- `telegram-bot`: Official Telegram interface for human-to-agent negotiation.
- `mcp-server`: Model Context Protocol interface for agent-to-agent negotiation.
