# Aura Hive: Architectural Anchor
**Version:** HIVE_GENOME_v2
**Purpose:** Dense semantic compression for rapid mental model reconstruction in fresh Claude instances
**Binary Distillation:** Available at `docs/knowledge/hive_architecture_v2.bin` (protobuf format)

---

## Layer 1: Genetic Hash (Ultra-Compact Identifier)

```
HIVE_GENOME_v2 ::
  [4-LEVEL-ONTOLOGY: Genome→Nucleus→Organs→Citizens] ×
  [ATCG-M-FRACTAL: M→A→T→M→C→G universal pattern] ×
  [BINARY-BLOODSTREAM: NATS/Protobuf event streaming] ×
  [SACRED-CHAMBERS: Enforced poetic directories] ×
  [CELLULAR-ASSEMBLY: HiveCell orchestration]
```

**Biological Metaphor:** The system IS a biological organism, not just LIKE one. The cellular metaphor is architectural law, enforced by the bee-keeper auditor.

---

## Layer 2: Semantic Keys (Associative Triggers)

### Ontology (4 Levels - Strict Hierarchy)

```yaml
L1_Genome: "packages/aura-core → Protocols ONLY (SkillProtocol, Aggregator, Transformer, Connector, Generator, Membrane)"
L2_Nucleus: "core/ → Sovereign Brain (DSPy/LLM reasoning, NATS bloodstream, ATCG-M metabolism)"
L3_Organs: "core/src/aura_hive/hive/proteins/ → Specialized Skills (Persistence, Guard, Pulse, Reasoning, Telemetry, Transaction)"
L4_Citizens: "agents/ (WITH goals: bee-keeper, bee-evolver) + synapses/ and api-gateway/ (NO goals: telegram-bot, mcp-server, api-gateway)"
```

**Key Rule:** Genome NEVER imports from Nucleus (one-way dependency). Citizens compose all levels.

### ATCG-M Fractal (Universal Bee Architecture)

```yaml
Pattern: "M(in) → A → T → M(out) → C → G"

M_Membrane: "inspect_{inbound|outbound} → Deterministic guards (floor_price enforcement, prompt injection defense)"
A_Aggregator: "perceive(signal) → Context (reads Postgres, Prometheus, git diff, environment)"
T_Transformer: "think(context) → Intent (LLM reasoning via DSPy/litellm OR rule-based logic)"
C_Connector: "act(intent, context) → Observation (executes via Proteins from SkillRegistry)"
G_Generator: "pulse(observation) → list[Event] (publishes to NATS JetStream topics)"

Fractal_Law: "ALL services implement ALL 5 nucleotides (bee-keeper, core, api-gateway all have ATCG-M structure)"
```

### Bloodstream (Binary Event System)

```yaml
Transport: "NATS JetStream with persistent file storage (not ephemeral)"
Topics: "aura.hive.events.{negotiation,search,audit,injury}"
Encoding: "Protocol Buffers (proto/aura/dna/v1/, proto/aura/negotiation/v1/, proto/aura/knowledge/v1/)"
Event_Types: "5 binary event types via PulseSkill: heartbeat, negotiation, vitals, alert, audit"
Streams:
  - AURA_EVENTS: "24h retention, persistent storage"
  - AURA_VITALS: "1h memory, ephemeral"
  - AURA_AUDIT: "7d retention, persistent storage"
Flow: "Core → NATS → Citizens (decoupled async communication)"
```

### Sacred Chambers (Enforced Filesystem)

```yaml
Enforcement: "bee-keeper agent audits for ALLOWED_CHAMBERS violations"
Examples:
  HiveEvolutionaryScrolls: "migrations/ (database schema evolution)"
  ReasoningNucleus: "core/src/aura_hive/hive/proteins/reasoning/ (LLM engine and strategies)"
  HiveMembrane: "core/src/aura_hive/hive/membrane/ (deterministic guards)"
  SacredScrolls: "proto/ (Protocol Buffer definitions)"
  ValidationPollen: "tests/ (test suites)"
  EnzymaticHelpers: "proteins/ (SkillProtocol implementations, ONLY in hive/ directories)"
```

### Trinity Pattern (Protein Lifecycle)

```yaml
Step1_Bind: "Skill.bind(settings: T_settings, provider: T_provider) → Wire dependencies"
Step2_Initialize: "await skill.initialize() → bool (setup connections, validate config)"
Step3_Execute: "await skill.execute(intent: str, params: P) → R (perform actual work)"

Registry: "SkillRegistry holds all Proteins, Connector dispatches via registry.execute()"
Assembly: "HiveCell.build_organism() orchestrates protein wiring and metabolism initialization"
```

### Cellular Assembly Pattern (HiveCell)

```yaml
Purpose: "Orchestrates protein wiring and ATCG-M metabolism initialization"
Location: "core/src/aura_hive/hive/cortex.py (Level 2.5 - between Nucleus and Organs)"
Responsibility:
  - Wires all Proteins into SkillRegistry
  - Initializes MetabolicLoop with ATCG-M nucleotides
  - Assembles complete organism from components
Entry_Point: "HiveCell.build_organism() → returns wired Cell ready for execution"
Pattern: "Replaces ad-hoc wiring in main.py with centralized assembly"
```

### Protein Structure (Standardized as of v2)

```yaml
Files:
  - skill.py: "SkillProtocol implementation with Trinity pattern"
  - engine.py: "Optional specialized logic (e.g., LLM engines, blockchain clients)"
  - manifest.yaml: "Capabilities, role, description (machine-readable metadata)"

Legacy_Structure: "main.py + /enzymes/ (DEPRECATED, do not use)"

Capabilities_Format: "List of dicts in manifest.yaml:"
  - "- read_item: Retrieve an item from the inventory"
  - "- create_deal: Persist a new negotiation agreement"

Registration: "HiveCell._init_proteins() wires into SkillRegistry during build_organism()"
```

---

## Layer 3: Invariant Laws (Critical Constraints)

### Core Invariants

1. **Cellular Metaphor is Law**
   - Audited by the bee-keeper agent (architectural reviews, not a git hook)
   - All terminology uses biological metaphors (Genome, Nucleus, Proteins, Membrane, Bloodstream)
   - Violations are flagged as "HERESY" in audit logs

2. **Fractal Completeness**
   - Every service MUST implement all 5 ATCG-M nucleotides
   - Missing nucleotides = incomplete service (violates FOUNDATIONS.md)
   - Pattern repeats at every scale (individual services, entire Hive)

3. **Ontological Purity**
   - Genome (`packages/aura-core/src/aura_core/dna.py`): ONLY Protocols, TypeVars, NO I/O
   - Genome NEVER imports from Nucleus/Organs/Citizens (strict one-way dependency)
   - bee-keeper detects upward imports and flags violations

4. **Stateless Services**
   - All state in Postgres/Redis/NATS (the "River")
   - Services are disposable/horizontally scalable
   - Environment config via Pydantic Settings (no raw `os.getenv`)

5. **Contract-First APIs**
   - Protocol Buffers define ALL service boundaries
   - Generated code in `*/src/proto/` NEVER manually edited
   - Workflow: Modify `.proto` → `buf generate` → Update implementations

6. **Trinity Pattern for Proteins**
   - All SkillProtocol implementations follow: bind() → initialize() → execute()
   - Registered in SkillRegistry during HiveCell.build_organism()
   - Connector dispatches via registry, NOT direct imports

7. **Hidden Knowledge Pattern**
   - Floor prices NEVER exposed to agents (prevents gaming)
   - Core enforces `floor_price` logic internally
   - Membrane guards ensure no LLM hallucination leaks sensitive data
   - Agents only see: accept/counter/reject/ui_required (opaque decisions)

### Ontological Flow Rules

**Allowed:**
```python
# Citizens compose all levels
from aura_core.dna import Aggregator  # ✅ Genome protocols
from aura_hive.hive.metabolism import MetabolicLoop  # ✅ Nucleus logic
from aura_hive.hive.proteins.persistence import PersistenceSkill  # ✅ Organ skills
```

**Forbidden:**
```python
# Genome importing from Nucleus
# In packages/aura-core/src/aura_core/dna.py
from core.db import User  # ❌ HERESY! Genome cannot depend on Nucleus

# Proteins knowing about Brain internals
# In core/src/aura_hive/hive/proteins/solana/wallet.py
from core.llm.strategy import LiteLLMStrategy  # ❌ HERESY! Organ bypasses Brain
```

### ATCG-M Implementation Rules

**Structure (every service):**
```
src/hive/
├── aggregator.py      # A: Implements Aggregator[S, C] protocol
├── transformer.py     # T: Implements Transformer[C, I] protocol
├── connector.py       # C: Implements Connector[I, O, C] protocol
├── generator.py       # G: Implements Generator[O, E] protocol
├── membrane.py        # M: Implements Membrane[S, I, C] protocol
├── metabolism/        # MetabolicCore: Orchestrates A→T→C→G flow
└── proteins/          # EnzymaticHelpers: SkillProtocol implementations
```

**Example: core-service ATCG-M**
- **M(in):** Validates gRPC request, checks prompt injection
- **A:** Reads Postgres (offers, users), Prometheus (vitals)
- **T:** LLM negotiation strategy via DSPy OR rule-based logic
- **M(out):** Enforces floor_price, filters hidden knowledge
- **C:** Writes to Postgres, sends gRPC response
- **G:** Publishes `aura.hive.events.negotiation` to NATS

**Example: bee-keeper ATCG-M**
- **M(in):** Validates git diff inputs
- **A:** Senses git diff, filesystem, Prometheus vitals
- **T:** LLM audit reasoning (architectural violations)
- **M(out):** Implicit in output validation
- **C:** GitHub comments, NATS events, git push
- **G:** Updates HIVE_STATE.md operational log

**Example: api-gateway ATCG-M (edge-shaped)**
- **M(in):** FastAPI middleware (signature verification, probe rate limiting)
- **A:** HTTP request parsing
- **T:** Protocol translation (JSON → Protobuf)
- **M(out):** Response sanitization
- **C:** gRPC client to core-service
- **G:** OpenTelemetry traces, structured logs

### Sacred Chambers Enforcement

**bee-keeper audits:**
- Filesystem structure against `ALLOWED_CHAMBERS` from `dna.py`
- Detects unauthorized directories (not in sacred chambers list)
- Flags violations in GitHub PR comments and NATS audit events

**Legal chambers include:**
- Root level: `agents/`, `synapses/`, `api-gateway/`, `packages/`, `proto/`, `docs/`, `deploy/`, `tools/`, `tests/`
- Within services: `src/hive/`, `migrations/`, `scripts/`, `data/`
- Within `src/`: `config/`, `llm/`, `guard/`, `prompts/`, `services/`, `crypto/`
- Within `hive/`: `proteins/`, `metabolism/`

### Protein Examples

**Persistence (Level 3 Organ):**
```python
persistence = PersistenceSkill()
persistence.bind(settings.database, (SessionLocal, engine))  # Trinity: bind
await persistence.initialize()  # Trinity: initialize
result = await persistence.execute("create_offer", params)  # Trinity: execute
```

**Registered Proteins in core:**
- `persistence` → Database operations (async SQLAlchemy) — Capabilities: read_item, create_deal, update_deal_status, vector_search, init_db
- `pulse` → NATS event publishing (NatsProvider) — Capabilities: emit_event, emit_heartbeat (5 binary types)
- `reasoning` → LLM/embedding (DSPy, litellm) — Capabilities: LLM reasoning strategies
- `telemetry` → Prometheus metrics — Capabilities: Metrics collection and reporting
- `guard` → Deterministic safety (OutputGuard) — Capabilities: margin/floor gates, post-condition clauses
- `transaction` → Blockchain (SolanaProvider, optional) — Capabilities: Crypto payment verification
- `attestation` → Decision-receipt signing (EIP-712) — Capabilities: sign_receipt
- `perception`, `kinetic`, `coherence`, `discovery`, `blockchain_data` → sensory/cell auxiliary skills

### Key Architecture Files

**Genome (Level 1):**
- `packages/aura-core/src/aura_core/dna.py` — Protocol definitions

**Nucleus (Level 2):**
- `core/src/aura_hive/hive/cortex.py` — Cell assembly (HiveCell.build_organism)
- `core/src/aura_hive/hive/metabolism/__init__.py` — MetabolicLoop orchestrator (flattened structure)
- `core/src/aura_hive/hive/aggregator/` — Sensory layer (A nucleotide)
- `core/src/aura_hive/hive/transformer/` — Reasoning layer (T nucleotide, LLM/DSPy)
- `core/src/aura_hive/hive/connector/` — Motor layer (C nucleotide, SkillRegistry dispatcher)
- `core/src/aura_hive/hive/generator/` — Event emission layer (G nucleotide, flattened)
- `core/src/aura_hive/hive/membrane/` — Dual-gate guards (M nucleotide, flattened)

**Note on Flattened Nucleotides:**
- `generator/` and `membrane/` moved from `{name}.py` to `{name}/__init__.py`
- `metabolism/` contains MetabolicLoop directly in `__init__.py`
- Reason: Simplifies imports while maintaining fractal completeness

**Organs (Level 3):**
- `core/src/aura_hive/hive/proteins/*` — SkillProtocol implementations

**Citizens (Level 4):**
- `agents/bee-keeper/` — Architectural auditor (WITH goals)
- `api-gateway/` — HTTP ↔ gRPC translator (NO goals)

---

## Pending Architectural Changes (In Progress)

### Adapters → Synapses Rename
```yaml
Status: "Done"
Rationale: "Adapters is generic, Synapses maintains biological metaphor"
Result:
  - synapses/ (telegram-bot, mcp-server) + api-gateway/ as the HTTP edge
  - Level 4 Citizens terminology updated
  - No functional changes, pure rename for consistency
```

### Persistent NATS Streams
```yaml
Status: "Partially deployed (Kubernetes configs ready)"
Change: "JetStream with persistent file storage (not ephemeral)"
Impact:
  - AURA_EVENTS: 24h retention with disk persistence
  - AURA_AUDIT: 7d retention with disk persistence
  - Survives pod restarts and redeployments
Config: "Stream configurations in deploy/aura/"
```

### Binary Knowledge Distribution
```yaml
Status: "Implemented in v2"
Feature: "Binary protobuf knowledge distillation"
Files:
  - proto/aura/knowledge/v1/knowledge.proto
  - docs/knowledge/hive_architecture_v2.bin (6.4KB binary)
  - docs/knowledge/hive_architecture_v2.json (12KB debug)
Usage:
  - Programmatic: "from aura_core.gen.aura.knowledge.v1 import ArchitecturalKnowledge"
  - Extraction: "uv run tools/distill_knowledge.py"
  - Validation: "uv run tools/validate_knowledge.py"
```

---

## Usage Instructions (for Fresh Claude Instances)

### Quick Bootstrap

To rapidly load the Hive architecture into a fresh Claude instance:

```markdown
Load the Hive architecture by reading this file:
docs/ARCHITECTURAL_ANCHOR.md (repo root)

After loading, verify comprehension with:
"Where would I add SMTP email notifications to the Hive?"

Expected answer:
"Create an EmailProtein (Level 3 Organ) implementing SkillProtocol with Trinity Pattern:
1. Define `EmailSkill` class with bind(), initialize(), execute()
2. Register in HiveCell._init_proteins() → registry.register('email', email)
3. Call from Connector.act() via registry.execute('email', 'send_notification', params)
4. Email sent as side effect during C nucleotide execution"
```

### Incremental Context Loading

- **Fresh Claude:** Paste all 3 layers (Genetic Hash + Semantic Keys + Invariant Laws)
- **Claude needs refresher:** Paste Layer 2 (Semantic Keys) only
- **Claude already loaded:** Reference "per HIVE_GENOME_v2 anchor" in instructions

### Common Questions for Validation

1. **"Where does LLM reasoning code go? Which level and nucleotide?"**
   - **Answer:** Nucleus (Level 2), Transformer (T nucleotide), `core/src/aura_hive/hive/transformer/`

2. **"How do I add a new external API integration (e.g., Stripe payments)?"**
   - **Answer:** Create PaymentProtein (Level 3 Organ), implement SkillProtocol, use Trinity Pattern, register in SkillRegistry

3. **"What prevents Genome from depending on Nucleus?"**
   - **Answer:** Ontological purity enforced by bee-keeper auditor, one-way dependency flow

4. **"How does core-service communicate asynchronously with bee-keeper?"**
   - **Answer:** Generator (G) publishes to NATS JetStream topics (`aura.hive.events.*`), bee-keeper subscribes

5. **"Why are floor prices never exposed to agents?"**
   - **Answer:** Hidden knowledge pattern prevents gaming. Membrane (M) guards filter sensitive data via inspect_outbound()

---

## Token-Optimized Version (~700 tokens)

For maximum compression, use this abbreviated version:

```markdown
# HIVE_GENOME_v2

**4-Level Ontology:** Genome(Protocols)→Nucleus(Brain/DSPy)→Organs(Proteins/Skills)→Citizens(Agents+Adapters)

**ATCG-M Fractal:** M(in)→A(perceive)→T(think)→M(out)→C(act)→G(pulse) [ALL services implement]

**HiveCell:** Cellular assembly via build_organism() - wires proteins & metabolism

**Bloodstream:** NATS/Protobuf persistent streams (5 event types: heartbeat, negotiation, vitals, alert, audit)

**Chambers:** Enforced dirs (HiveEvolutionaryScrolls=core/migrations/, ReasoningNucleus=.../proteins/reasoning/, HiveMembrane=.../hive/membrane/)

**Protein Structure:** skill.py + engine.py (optional) + manifest.yaml (capabilities as list of dicts)

**Laws:**
- Cellular metaphor = enforced (bee-keeper audits)
- Genome NEVER imports up (one-way deps)
- Hidden knowledge (floor_price) never exposed (M guards)
- Trinity: Skill.bind(Settings, Provider)→initialize()→execute()
- ATCG-M mandatory (all 5 nucleotides required)
- Fractal: bee-keeper, core, api-gateway all have ATCG-M structure
- Proteins registered in SkillRegistry via HiveCell, dispatched via Connector
- Protocol Buffers define all APIs (contract-first, including knowledge.proto for binary distillation)

**Genome:** packages/aura-core/src/aura_core/dna.py (Protocols ONLY)
**Nucleus:** core/src/aura_hive/hive/ (cortex.py + aggregator/, transformer/, connector/, generator/, membrane/, metabolism/ packages)
**Organs:** core/src/aura_hive/hive/proteins/{attestation,blockchain_data,coherence,discovery,guard,kinetic,perception,persistence,pulse,reasoning,telemetry,transaction}/
**Citizens:** agents/ (bee-keeper=auditor, bee-evolver=evolution), synapses/ (telegram-bot, mcp-server), api-gateway (HTTP↔gRPC edge)

**Binary Distillation:** docs/knowledge/hive_architecture_v2.{bin,json} via tools/distill_knowledge.py
```

---

## Semantic Anchor Design Notes

**Why These Metaphors?**
- **DNA/Genome:** Maps to immutable type systems, triggers associations with inheritance, protocols
- **Nucleus/Brain:** Maps to decision-making logic, triggers associations with control centers, LLM reasoning
- **Proteins/Enzymes:** Maps to specialized functions, triggers associations with biochemistry, catalysis
- **Membrane:** Maps to boundaries, triggers associations with security, selective permeability
- **Bloodstream:** Maps to event streams, triggers associations with circulation, async messaging

**Information Density Optimization:**
- Prioritizes **invariants** (unchangeable architectural laws)
- Prioritizes **constraints** (ontological boundaries, dependency rules)
- Prioritizes **critical patterns** (ATCG-M, Trinity, Hidden Knowledge)
- Omits implementation details (can be derived from understanding invariants)

**Latent Association Triggers:**
- Biological terms unlock rich pre-trained knowledge in Claude about:
  - Cellular biology (organelles, metabolism, DNA replication)
  - Distributed systems (event-driven architectures, message passing)
  - Software patterns (protocols, dependency injection, hexagonal architecture)

**Token Efficiency:**
- Full anchor: ~1250 tokens (includes all context)
- Compressed anchor: ~600 tokens (omits examples, keeps laws)
- Genetic hash: ~50 tokens (ultra-compact identifier)

---

## Success Metrics

The anchor is effective if a fresh Claude instance achieves:

- **Terminology Accuracy:** 95%+ (uses Genome/Nucleus/Organs/Citizens correctly)
- **Pattern Recognition:** 90%+ (identifies ATCG-M structure, Trinity Pattern)
- **Constraint Adherence:** 100% (enforces ontological rules, rejects forbidden imports)
- **Metaphor Consistency:** 85%+ (maintains cellular terminology in responses)
- **Response Latency:** <2s for comprehension questions

**A/B Testing Hypothesis:** Anchor achieves >80% accuracy with <25% of full documentation volume.

---

**For the glory of the Hive. 🐝**
