---
sidebar_position: 1
---

# Architecture Overview

Aura Hive is built on biological metaphors, creating a self-organizing system of AI agents called **Proteins** that process **Signals** through a fractal **ATCG-M** protocol pattern.

## Core Components

### 1. Proteins (AI Agents)
Self-contained units that implement one or more ATCG-M protocols. Each Protein:
- Has a unique identity and capabilities
- Communicates via the Binary Bloodstream (NATS)
- Processes signals through its metabolism
- Maintains internal state and memory

Examples:
- **NegotiationProtein**: Handles bid/offer flows
- **SkillProtein**: Orchestrates external capabilities
- **NLUProtein**: Natural language understanding

### 2. ATCG-M Protocols
Five nucleotide patterns that combine fractally:

- **A (Aggregator)**: Gathers context and data
- **T (Transformer)**: Makes decisions and transforms signals
- **C (Connector)**: Routes messages to destinations
- **G (Generator)**: Emits events and side effects
- **M (Membrane)**: Enforces sovereignty and constraints

See [ATCG-M Metabolism](atcg-metabolism) for detailed explanation.

### 3. Binary Bloodstream
NATS-based message bus connecting all proteins:
- **Subjects**: Hierarchical topic structure (e.g., `hive.protein.negotiate.request`)
- **Streams**: Persistent event storage with replay capability
- **JetStream**: Exactly-once delivery guarantees
- **KV Store**: Distributed state management

### 4. DNA (Type System)
Protobuf-defined types shared across all components:

```protobuf
message Signal {
  Context context = 1;
  Intent intent = 2;
}

message Context {
  string session_id = 1;
  map<string, string> metadata = 2;
}

message Intent {
  string action = 1;
  google.protobuf.Struct params = 2;
}
```

All proteins speak the same type language, enabling seamless composition.

## System Layers

```
┌─────────────────────────────────────────────┐
│          Frontend (React/TypeScript)        │
│  User Interface + Signal Construction       │
└──────────────────┬──────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────┐
│         API Gateway (FastAPI)               │
│  HTTP → Signal → NATS → HTTP                │
└──────────────────┬──────────────────────────┘
                   │ NATS Messages
┌──────────────────▼──────────────────────────┐
│      Binary Bloodstream (NATS)              │
│  Subject Routing + Event Streaming          │
└──────────┬────────────────┬─────────────────┘
           │                │
┌──────────▼────────┐  ┌───▼─────────────────┐
│  Proteins Layer   │  │  Skills Layer       │
│  (Python Agents)  │  │  (External Tools)   │
│  - Negotiate      │  │  - Stripe           │
│  - NLU            │  │  - SendGrid         │
│  - Skill          │  │  - Custom APIs      │
└───────────────────┘  └─────────────────────┘
```

## Data Flow Example: Negotiation

1. **User Action**: User clicks "Make Bid" in frontend
2. **Signal Construction**: Frontend creates `NegotiateRequest` with bid amount
3. **API Gateway**: Converts HTTP to NATS message on `hive.protein.negotiate.request`
4. **NegotiationProtein**:
   - **M(in)**: Validates bid against rules
   - **A**: Aggregates item data, user history
   - **T**: Decides outcome (accept/counter/reject)
   - **M(out)**: Enforces business constraints
   - **C**: Routes response back to gateway
   - **G**: Emits `bid_placed` event
5. **API Gateway**: Converts NATS response to HTTP
6. **Frontend**: Updates UI with result

## Key Design Principles

### 1. Fractal Composition
The same ATCG-M pattern applies at every scale:
- Single function (validate input → transform → return)
- Single protein (M → A → T → M → C → G)
- Multi-protein workflow (orchestrated via events)

### 2. Type-First Development
All interfaces defined in Protobuf before implementation:
- Frontend generates TypeScript types
- Backend generates Python types
- Perfect sync between layers

### 3. Event Sourcing
All state changes captured as events:
- Audit trail by default
- Replay for debugging
- Analytics from event stream

### 4. Punk Sovereignty
Every protein has boundaries enforced by Membrane:
- Rate limiting
- Permission checks
- Business rule validation
- Circuit breakers

## Deployment Architecture

```
┌─────────────────────────────────────────────┐
│           Railway (Production)              │
│  ┌─────────────┐  ┌────────────────────┐   │
│  │ Frontend    │  │ Backend            │   │
│  │ (React)     │  │ (FastAPI + Uvicorn)│   │
│  └─────────────┘  └───────┬────────────┘   │
│                            │                │
│  ┌─────────────────────────▼─────────────┐  │
│  │        NATS (JetStream)               │  │
│  │  - Message routing                    │  │
│  │  - Event persistence                  │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │      PostgreSQL                       │  │
│  │  - User data                          │  │
│  │  - Item catalog                       │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

## Technology Choices

| Layer | Technology | Why? |
|-------|------------|------|
| Frontend | React + TypeScript | Type safety, ecosystem |
| Backend | FastAPI + Python | Async, Protobuf support, AI libs |
| Message Bus | NATS JetStream | Simplicity, performance, persistence |
| Database | PostgreSQL | Reliability, JSON support |
| AI | OpenAI API | Claude via compatible endpoint |
| Schema | Protobuf | Cross-language types |
| Infra | Railway | Easy deploy, preview envs |

## Next Steps

- Learn the [ATCG-M pattern](atcg-metabolism) in depth
- Explore the [visual guides](../visual) for diagrams
- Try the [interactive simulator](../interactive/negotiation-simulator)
- Read about the [Binary Bloodstream](binary-bloodstream)
