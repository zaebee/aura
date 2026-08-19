---
sidebar_position: 1
slug: /
---

# Welcome to Aura Hive

**Punk-Sovereign AI Infrastructure**

Aura Hive is a biological-inspired AI orchestration platform that implements a fractal protocol pattern called **ATCG-M** (Aggregator, Transformer, Connector, Generator, Membrane). Like DNA nucleotides, these protocols combine to create complex behaviors through simple, composable units.

## What Makes Hive Different?

### 1. Biological Architecture
Instead of traditional microservices, Hive uses:
- **Proteins**: Self-contained AI agents that implement ATCG-M protocols
- **Metabolism**: Signal processing flow through the nucleotide pattern
- **Binary Bloodstream**: NATS-based event streaming backbone
- **Membrane**: Sovereignty layer enforcing constraints and permissions

### 2. Fractal Protocol Pattern
Every component implements the same interface at different scales:
```
User Request → M(in) → A → T → M(out) → C → G → Response
              ↓        Skill Processing        ↓
            Validate                        Store
```

### 3. Type-Safe DNA
All protocols share a common type system defined in Protobuf:
- **Signal**: User intent with context
- **Intent**: Classified action request
- **Observation**: Processing result
- **Event**: State change notification

## Quick Navigation

### For Architects
- [Architecture Overview](/docs/architecture/overview) - System design and principles
- [ATCG-M Metabolism](/docs/architecture/atcg-metabolism) - Core protocol pattern
- [Binary Bloodstream](/docs/architecture/binary-bloodstream) - Message transport layer

### For Developers
- [Protocol Implementations](/docs/protocols/atcg-overview) - How to implement each nucleotide
- [API Reference](/docs/api/dna-reference) - Protobuf type definitions
- [Interactive Simulator](/docs/interactive/negotiation-simulator) - Try the metabolism flow

### For Visual Learners
- [Visual Guides](/docs/visual) - Mermaid diagrams and flowcharts
- [Hive Geography](/docs/visual/hive/geography) - Where everything lives
- [Metabolism Flow](/docs/visual/metabolism) - Signal processing visualization

## Key Concepts

| Concept | Description | Analogy |
|---------|-------------|---------|
| **Protein** | Self-contained AI agent implementing ATCG-M | Cell organelle |
| **ATCG-M** | Five protocol nucleotides for signal processing | DNA bases |
| **Binary Bloodstream** | NATS event stream connecting proteins | Circulatory system |
| **Membrane** | Sovereignty enforcement layer | Cell membrane |
| **Skill** | External capability invoked by Generator | Enzyme |

## Example: Negotiation Flow

When a user makes a bid, the signal flows through the metabolism:

1. **M(in)**: Membrane validates bid against floor price
2. **A**: Aggregator collects item data, user history, market context
3. **T**: Transformer decides: accept/counter/reject/ui_required
4. **M(out)**: Membrane enforces business rules (e.g., minimum counter)
5. **C**: Connector sends response to frontend
6. **G**: Generator emits events (bid_placed, counter_offered, etc.)

See it in action: [Interactive Negotiation Simulator](/docs/interactive/negotiation-simulator)

## Get Started

1. **Understand the Architecture**: Read the [architecture overview](/docs/architecture/overview) for system design principles
2. **Learn ATCG-M**: Study the [protocol pattern](/docs/protocols/atcg-overview) and see [visual examples](/docs/visual/metabolism)
3. **Explore the Code**: Browse the [API reference](/docs/api/dna-reference) to understand types
4. **Build a Protein**: Follow the protocol implementations to create your own agent

## System Requirements

- **Backend**: Python 3.11+ with UV package manager
- **Frontend**: Node.js 20+ with Bun or pnpm
- **Message Bus**: NATS server (2.10+)
- **Database**: PostgreSQL 15+
- **Protobuf**: buf CLI for schema management

## Technology Stack

- **Backend**: FastAPI + Protobuf + NATS
- **Frontend**: React + TypeScript + TanStack Query
- **AI**: OpenAI API (Claude via OpenAI-compatible endpoint)
- **Infra**: Docker Compose for local dev, Railway for staging

## Community & Support

- **GitHub**: [zaebee/aura](https://github.com/zaebee/aura)
- **Issues**: Report bugs and request features
- **Discussions**: Share ideas and ask questions

---

*For the glory of the Hive.* 🐝
