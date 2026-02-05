---
sidebar_position: 1
---

# ATCG-M Protocol Overview

The ATCG-M pattern defines five protocol nucleotides that every Protein implements. This page provides an overview and links to detailed implementations.

## The Five Nucleotides

| Protocol | Purpose | Key Responsibility |
|----------|---------|-------------------|
| [M (Membrane)](membrane) | Input validation | Enforce sovereignty, validate inputs |
| [A (Aggregator)](aggregator) | Context gathering | Fetch all data needed for decisions |
| [T (Transformer)](transformer) | Decision making | Core business logic and transformations |
| [M (Membrane)](membrane) | Output validation | Validate responses, enforce post-conditions |
| [C (Connector)](connector) | Routing | Send responses to destinations |
| [G (Generator)](generator) | Events & side effects | Emit events, invoke skills |

## Complete Flow

```
User Signal → M(in) → A → T → M(out) → C → G → Events
```

## Implementation Pattern

Every Protein follows this structure:

```python
class MyProtein:
    def membrane_in(self, signal: Signal) -> Signal:
        # Validation
        pass

    async def aggregator(self, signal: Signal) -> EnrichedSignal:
        # Context gathering
        pass

    def transformer(self, enriched: EnrichedSignal) -> Decision:
        # Business logic
        pass

    def membrane_out(self, decision: Decision) -> Response:
        # Output validation
        pass

    async def connector(self, response: Response, signal: Signal):
        # Routing
        pass

    async def generator(self, response: Response, signal: Signal):
        # Events
        pass
```

## Next Steps

- Learn each protocol in detail:
  - [Aggregator](aggregator)
  - [Transformer](transformer)
  - [Connector](connector)
  - [Generator](generator)
  - [Membrane](membrane)
- See [metabolism diagram](../visual/metabolism)
- Try the [simulator](../interactive/negotiation-simulator)
