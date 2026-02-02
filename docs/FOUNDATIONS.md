# 🏛️ Aura Hive Foundations: The Sovereign Architecture

## 🧬 1. The Ontological Hierarchy
Every element of the Hive exists at one of four levels:

1. **Level 1: The Genome (`/packages/aura-core`)**
   - **Status:** Immutable DNA.
   - **Content:** Pure Python `Protocols`, `BaseModels`, and `Type` definitions.
   - **Rule:** No business logic. No external I/O. This is the shared language of all Bees.

2. **Level 2: The Nucleus (`/core`)**
   - **Status:** The Sovereign Brain.
   - **Content:** The ATCG-M metabolism implementation for decision making.
   - **Rule:** Uses the Genome to reason. Communicates via NATS "Bloodstream".

3. **Level 3: The Organs (`/components/proteins`)**
   - **Status:** Specialized Skills.
   - **Content:** Reusable adapters for external worlds (Solana, Telegram, GitHub, Prometheus).
   - **Rule:** Implements specific `SkillProtocols`. Decoupled from the Brain.

4. **Level 4: The Citizens (`/agents` & `/adapters`)**
   - **Status:** Active Subjects & Passive Servants.
   - **Content:** Composed entities (Brain + specific Proteins).
   - **Rule:** Agents (Keeper, Chronicler) have goals. Adapters (Gateway, Bot) only translate signals.

## 🕸️ 2. The ATCG-M Metabolism
Every "Bee" (Service) MUST follow this fractal structure:
- **A (Aggregator):** Collects senses/data. (Sensory Input)
- **T (Transformer):** Reasons via Ona (LLM/DSPy). Uses `<think>` blocks. (Cognitive Process)
- **C (Connector):** Acts via Jules (Proteins/IO). (Motor Output)
- **G (Generator):** Pulses events to NATS. (Nervous Signal)
- **M (Membrane):** Deterministic safety guards. (Immune System)

## 🛡️ 3. The 12-Factor Hive Law
- **Statelessness:** All bees are disposable. Memory lives in the River (Postgres/Redis).
- **Environment:** Configuration via `AURA_SECTION__VAR` (Pydantic V2). No raw `os.getenv`.
- **Logs as Events:** Structured JSON logging (`structlog`).
- **Nervous System:** Asynchronous communication via NATS Bloodstream.

## 🔬 4. Genetic Integrity & Pattern Purity
To maintain the sanctity of the Hive, the `bee.Keeper` performs automated architectural audits.
- **Pattern Heresy:** Detecting deviations from the ATCG-M structure or direct I/O bypassing the Connector.
- **Root Sanctification:** Ensuring the Macro-ATCG root directory remains free of foreign sprouts.
- **Sacred Chambers:** Validating that business logic and infrastructure reside in their sanctified chambers.
