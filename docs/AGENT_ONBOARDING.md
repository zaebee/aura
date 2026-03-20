# Agent Onboarding Manual: Working in the Bio-Digital Hive

> **CRITICAL FIRST STEP:** Always pull the latest `main` branch before mutating the codebase. See [Mutation Safety Protocol](#mutation-safety-protocol) for details.

Welcome to the Aura Hive. This document teaches AI agents how to work in this biologically-inspired codebase. The Hive is a living organism—treat it with the same care you would a biological system.

---

## Table of Contents

1. [The A2C10 & ENA Framework](#the-a2c10--ena-framework)
2. [The DNA Structure](#the-dna-structure)
3. [The Chromosomal Split](#the-chromosomal-split)
4. [Mutation Safety Protocol](#mutation-safety-protocol)
5. [Quick Reference](#quick-reference)

---

## The A2C10 & ENA Framework

### Biological Metaphor

The Aura codebase treats software as a **living organism**. Every component has a biological analog:

| Component | Biological Role | Function |
|-----------|----------------|----------|
| **Aggregator (A)** | **Senses** | Receives Signals from the external world, converts raw stimuli into meaningful Context |
| **Transformer (T)** | **Brain** | Processes Context into Intent using DSPy-powered reasoning |
| **Membrane** | **Immune System** | Validates inbound Signals and outbound Intents, blocks malicious/invalid data |
| **Connector (C)** | **Motor Nervous System** | Executes Intent by coordinating Skills (Proteins) |
| **Generator (G)** | **Endocrine System** | Emits Events to the bloodstream (NATS JetStream) |
| **Skills/Proteins** | **Organs** | Specialized functional units (Guard, Reasoning, Persistence, etc.) |

### The ATCG Metabolic Cycle

Information flows through the Hive in a continuous metabolic cycle:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        THE METABOLIC LOOP                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────┐    ┌───────────┐    ┌────────────┐    ┌─────────┐ │
│   │  Signal  │───▶│ Membrane  │───▶│ Aggregator │───▶│Context  │ │
│   │  (Input) │    │ (Inbound) │    │   (A)      │    │         │ │
│   └──────────┘    └───────────┘    └────────────┘    └────┬────┘ │
│                                                            │       │
│   ┌────────────┐    ┌──────────┐    ┌────────────┐       │       │
│   │  Observation│◀───│ Connector│◀───│ Transformer│◀──────┘       │
│   │            │    │   (C)    │    │    (T)     │               │
│   └─────┬──────┘    └──────────┘    └──────┬─────┘               │
│         │                                    │                     │
│   ┌─────▼──────┐                            │                     │
│   │  Generator │◀───────────────────────────┘                     │
│   │    (G)      │    Membrane (Outbound)                           │
│   └────────────┘                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### ENA Protocol

**ENA (External Neural Architecture)** is the strict typing system that governs all communication within the Hive:

- **All inter-component communication uses Protocol Buffers (Protobuf)**
- **NO raw JSON in the bloodstream** (NATS JetStream)
- **Strict oneof payloads** prevent ambiguity
- **Binary serialization** for performance and type safety

---

## The DNA Structure

### Protocol Definition Files

The Hive's DNA is defined in `.proto` files located in `proto/aura/`:

```
proto/aura/
├── dna/v1/
│   ├── dna.proto              # Core Signal, Context, Intent, Observation, Event
│   └── trace.proto           # Distributed tracing context
├── core/v1/
│   ├── base.proto            # ActionType, VitalsStatus enums
│   └── metabolism.proto      # TradeIntent, RWAVaultIntent, RWAComplianceScore
├── negotiation/v1/
│   └── negotiation.proto     # gRPC NegotiationService
├── assets/v1/
│   └── assets.proto          # Physical asset definitions (Chromosomal split)
└── knowledge/v1/
    └── knowledge.proto       # Vector embedding schemas
```

### Core DNA Messages

#### Signal (A - Aggregator Input)

```protobuf
message Signal {
  string signal_id = 1;
  SignalType signal_type = 2;
  google.protobuf.Timestamp timestamp = 3;
  
  oneof payload {
    NegotiationSignal negotiation = 10;
    PerceptionSignal perception = 14;  // Vision AI input
  }
}
```

#### Context (Aggregated Understanding)

```protobuf
message Context {
  string context_id = 1;
  ContextType context_type = 2;
  SystemVitals system_health = 3;
  map<string, string> metadata = 4;  // Key-value enrichment
  
  oneof data {
    HiveContextData hive = 10;
  }
}
```

#### Intent (T - Transformer Output)

```protobuf
message Intent {
  string intent_id = 1;
  ActionType action = 2;
  string reasoning = 3;  // Contains <think>...</think> tags
  
  oneof params {
    NegotiationIntent negotiation = 10;
    RWAVaultIntent rwa_vault = 15;  // ERC-8004 RWA vault intent
    TradeIntent trade = 16;         // ERC-8004 trade intent
  }
}
```

### RWA (Real World Asset) DNA

The **ERC-8004 RWA compliance** is encoded in the DNA:

```protobuf
message RWAVaultIntent {
  string vault_id = 1;
  string asset_identifier = 2;
  string asset_domain = 3;           // "GOLD", "ROLEX", "REAL_ESTATE"
  double appraised_value_usd = 4;
  double ltv_ratio = 5;              // Default 0.60
  double collateral_value_usd = 6;  // appraised * ltv
  string stablecoin_currency = 7;   // "USDC"
  string wallet_address = 8;
  RWAComplianceScore compliance = 9;
}

message RWAComplianceScore {
  bool kyc_passed = 1;
  bool aml_passed = 2;
  string compliance_status = 3;  // "APPROVED", "REJECTED", "PENDING"
  string violation_code = 4;     // "KYC_MISSING", "AML_SUSPICIOUS"
}
```

### Why Protobuf? Why Not JSON?

| Aspect | Protobuf | JSON |
|--------|----------|------|
| **Type Safety** | ✅ Strict schemas | ❌ Dynamic typing |
| **Performance** | ✅ Binary serialization | ❌ Text parsing |
| **Evolution** | ✅ Field numbers, optional fields | ⚠️ Backward compat issues |
| **Code Gen** | ✅ Multi-language (Python, Go, Rust, TS) | ⚠️ Manual parsing |
| **Bloodstream** | ✅ NATS JetStream optimized | ❌ Bloats message size |

---

## The Chromosomal Split

The codebase underwent a **v0.3.1 Chromosomal Split** to separate concerns:

### Core Chromosome (`core/`)

Contains the **metabolic engine**—the thinking, sensing, and acting components:

```
core/
├── src/hive/
│   ├── aggregator/          # A - Signal to Context conversion
│   ├── transformer/         # T - DSPy reasoning engine
│   │   ├── main.py         # AuraTransformer
│   │   ├── signatures.py   # DSPy signatures (AppraiseAndVerifyRWA)
│   │   └── engine.py       # AuraRWANegotiator, AuraTradeNegotiator
│   ├── membrane/           # Immune system validation
│   ├── proteins/           # Skills/Proteins (Guard, Reasoning, etc.)
│   ├── connector/          # C - Action execution
│   └── generator/          # G - Event emission
├── tests/                  # Integration tests
└── config/                # Policy settings
```

### Asset Chromosome (`proto/aura/assets/v1/`)

Contains **physical asset definitions**—the "body" of the organism:

```
proto/aura/assets/v1/
├── assets.proto           # Physical asset types
├── valuation.proto        # Appraisal methodologies
└── custody.proto         # Custody chain definitions
```

### DNA Chromosome (`proto/aura/dna/v1/`)

Contains **universal protocols**—the genetic code shared by all:

```
proto/aura/dna/v1/
├── dna.proto              # Signal, Context, Intent, Observation, Event
└── trace.proto           # W3C Trace Context propagation
```

---

## Mutation Safety Protocol

### Critical Rules for AI Agents

> ⚠️ **MERGE CONFLICTS = CYTOKINE STORMS**
>
> When multiple agents mutate the codebase simultaneously, conflicting changes cause "Cytokine Storms"—catastrophic merge conflicts that can kill the organism.

#### Rule 1: Always Pull Latest Main

```bash
# BEFORE any mutation
git pull origin main
git status
```

#### Rule 2: Never Modify dna.proto Unless Explicitly Instructed

The DNA is the most sensitive part of the organism. Changes here cascade through ALL services.

**Exceptions** (only when explicitly requested):
- Adding new Signal types for new input channels
- Adding new Intent types for new action types
- Schema evolution with proper field numbering

#### Rule 3: Coordinate with Active Agents

Before making significant changes, check for active agents:

```bash
# Check recent commits and active branches
git log --oneline -10
git branch -a
```

#### Rule 4: Test Before Commit

```bash
# Run the RWA integration test
cd core && uv run pytest tests/test_rwa_stablehacks_flow.py -v

# Run the full test suite
make test
```

#### Rule 5: Use ProtoGen for Schema Changes

If you MUST modify proto files:

```bash
# Generate Python code from proto
cd proto && buf generate

# Verify generated code compiles
cd core && uv run python -c "from aura_core_gen.aura.core.v1 import *"
```

---

## Quick Reference

### Key Entry Points

| Component | File | Purpose |
|-----------|------|---------|
| **MetabolicLoop** | `packages/aura-core/src/aura_core/metabolism.py` | ATCG loop orchestration |
| **AuraTransformer** | `core/src/hive/transformer/main.py` | DSPy reasoning (RWA, Trade, Negotiation) |
| **HiveMembrane** | `core/src/hive/membrane/main.py` | KYC/AML validation, DLP checks |
| **GuardSkill** | `core/src/hive/proteins/guard/skill.py` | Transaction safety validation |
| **AuraRWANegotiator** | `core/src/hive/proteins/reasoning/engine.py` | ERC-8004 compliance reasoning |

### Running Tests

```bash
# Install dependencies
uv sync
uv sync --group dev

# Run specific test
cd core && uv run pytest tests/test_rwa_stablehacks_flow.py -v

# Run with coverage
make test-cov

# Run lint
make lint
```

### Environment Variables

```bash
# Core Configuration
AURA_DATABASE__URL=postgresql://user:pass@localhost:5432/aura_db
AURA_LLM__MODEL=mistral/mistral-large-latest  # or "rule" for no LLM

# RWA Configuration
AURA_SAFETY__RWA_LTV_RATIO=0.60  # 60% loan-to-value
```

### Common Patterns

#### Adding a New Skill (Protein)

1. Create `core/src/hive/proteins/<name>/skill.py`
2. Implement `SkillProtocol` interface
3. Register in `core/src/hive/cortex.py`
4. Add tests in `core/tests/`

#### Adding a New DSPy Signature

1. Define signature in `core/src/hive/transformer/signatures.py`
2. Implement module in `core/src/hive/proteins/reasoning/engine.py`
3. Wire in `AuraTransformer._think_*()` methods
4. Add integration test

#### RWA Compliance Check Flow

```
Signal.metadata["rwa_mode"] = "true"
    ↓
AuraTransformer._think_rwa()
    ↓
AuraRWANegotiator.forward() → DSPy reasoning
    ↓
RWAComplianceScore{kyc_passed, aml_passed}
    ↓
HiveMembrane.inspect_outbound() → blocks if !kyc_passed
    ↓
GuardSkill.validate_transaction()
    ↓
Solana transaction / Observation
```

---

## Emergency Contacts

If something goes wrong:

1. **bee.jules**: Core metabolism expert
2. **bee.ona**: RWA/ERC-8004 specialist  
3. **bee.claude**: Integration testing
4. **bee.mistral**: LLM/DSPy reasoning

---

*Document Version: 1.0.0 (StableHacks Sprint)*
*Last Updated: 2026-03-20*
