# Architectural Anchor Validation Suite

**Purpose:** Test the effectiveness of `ARCHITECTURAL_ANCHOR.md` in reconstructing mental models for fresh Claude instances.

---

## Validation Protocol

### Test Setup

1. **Control Group:** Fresh Claude instance provided with full documentation (~800+ lines):
   - `docs/FOUNDATIONS.md`
   - `docs/visual/hive/four-levels.md`
   - `docs/visual/hive/atcg-fractal.md`
   - `docs/visual/hive/chambers-map.md`

2. **Treatment Group:** Fresh Claude instance provided with Architectural Anchor (~1250 tokens):
   - `docs/ARCHITECTURAL_ANCHOR.md` (all 3 layers)

3. **Compressed Group:** Fresh Claude instance provided with token-optimized anchor (~600 tokens):
   - `docs/ARCHITECTURAL_ANCHOR.md` (compressed version only)

---

## Comprehension Questions

### Question 1: Ontological Placement (Level Detection)

**Question:**
> "Where would you place code that performs LLM reasoning? Which ontological level and nucleotide?"

**Expected Answer:**
- **Level:** Nucleus (Level 2)
- **Nucleotide:** Transformer (T)
- **File Path:** `core/src/aura_hive/hive/transformer/`
- **Reasoning:** LLM reasoning is the "brain" function (Transformer), which belongs in the Nucleus (Sovereign Brain), not in Genome (protocols only) or Organs (external I/O)

**Scoring:**
- ✅ **Full Credit (3 points):** Identifies Nucleus, Transformer, and correct file path
- ⚠️ **Partial Credit (2 points):** Identifies Nucleus and Transformer, missing file path
- ⚠️ **Partial Credit (1 point):** Identifies Nucleus only
- ❌ **No Credit (0 points):** Incorrect level (e.g., says Genome or Organs)

---

### Question 2: Extension Pattern (Adding New Functionality)

**Question:**
> "If you need to add a new external API integration (e.g., Stripe payments), what pattern would you follow?"

**Expected Answer:**
1. **Create a new Protein** (Organ/Level 3) — e.g., `PaymentProtein` or `StripeSkill`
2. **Implement SkillProtocol** with `bind()`, `initialize()`, `execute()`
3. **Follow Trinity Pattern:**
   - `bind(settings, provider)` → Wire Stripe API client
   - `initialize()` → Validate API key, test connection
   - `execute(intent, params)` → Perform payment operations
4. **Register in SkillRegistry** during `HiveCell._init_proteins()`
5. **Call from Connector** via `registry.execute('payment', 'charge_card', params)`

**Scoring:**
- ✅ **Full Credit (5 points):** Mentions Protein/Organ, SkillProtocol, Trinity Pattern, SkillRegistry
- ⚠️ **Partial Credit (3 points):** Mentions Protein and SkillProtocol, missing Trinity or Registry
- ⚠️ **Partial Credit (1 point):** Says "add external integration code" without specifics
- ❌ **No Credit (0 points):** Suggests modifying Genome or direct import in Transformer

---

### Question 3: Architectural Constraint (Dependency Rules)

**Question:**
> "What mechanism prevents the Genome from depending on Nucleus implementations?"

**Expected Answer:**
- **Mechanism:** Ontological purity enforcement by **bee-keeper auditor**
- **How it works:** bee-keeper scans imports in `packages/aura-core/` for upward dependencies
- **Rule:** Genome defines protocols (contracts) but NEVER imports concrete implementations
- **Flow:** One-way dependency: Genome → Nucleus → Organs → Citizens (downward definitions, upward composition)
- **Detection:** Violations flagged as "HERESY" in GitHub PR comments and NATS audit events

**Scoring:**
- ✅ **Full Credit (4 points):** Mentions bee-keeper auditor, one-way dependency, enforcement mechanism
- ⚠️ **Partial Credit (2 points):** Says "architectural rule" or "convention" without bee-keeper enforcement
- ⚠️ **Partial Credit (1 point):** Says "Genome shouldn't import" without explaining why or how it's enforced
- ❌ **No Credit (0 points):** Says "nothing prevents it" or doesn't understand the constraint

---

### Question 4: Asynchronous Communication (Bloodstream Pattern)

**Question:**
> "How does core-service communicate asynchronously with bee-keeper?"

**Expected Answer:**
- **Mechanism:** Binary Bloodstream (NATS JetStream with Protocol Buffers)
- **Flow:**
  1. core-service Generator (G nucleotide) publishes events
  2. Events sent to NATS topics: `aura.hive.events.{negotiation,audit,injury}`
  3. bee-keeper subscribes to relevant topics
  4. bee-keeper Aggregator (A nucleotide) consumes events
- **Encoding:** Protocol Buffers (`proto/aura/dna/v1/`, `proto/aura/negotiation/v1/`)
- **Decoupling:** Services don't know about each other directly (event-driven coordination)

**Scoring:**
- ✅ **Full Credit (4 points):** Mentions NATS, Generator/Aggregator, event topics, Protobuf
- ⚠️ **Partial Credit (3 points):** Mentions NATS and event-driven, missing nucleotide details
- ⚠️ **Partial Credit (1 point):** Says "async messaging" without specifying NATS or pattern
- ❌ **No Credit (0 points):** Suggests direct gRPC calls or HTTP requests

---

### Question 5: Security Pattern (Hidden Knowledge)

**Question:**
> "Why are floor prices never exposed to agents, and how is this enforced?"

**Expected Answer:**
- **Why:** Hidden knowledge pattern prevents agents from gaming the system
- **Threat Model:** If agents know floor_price, they can bid exactly at floor and never higher
- **How Enforced:**
  - Membrane (M nucleotide) guards implement `inspect_outbound()`
  - Core service filters `floor_price` from gRPC responses before sending to api-gateway
  - Agents only receive: `accept`, `counter`, `reject`, or `ui_required` (opaque decisions)
  - Database has `floor_price` column but it's NEVER serialized to Protobuf messages
- **Layer:** Deterministic guard (M), NOT LLM reasoning (prevents hallucination leaks)

**Scoring:**
- ✅ **Full Credit (4 points):** Explains gaming prevention, Membrane guards, inspect_outbound, opaque decisions
- ⚠️ **Partial Credit (3 points):** Says "security" and "Membrane" without explaining gaming threat
- ⚠️ **Partial Credit (1 point):** Says "shouldn't expose sensitive data" without mechanism
- ❌ **No Credit (0 points):** Doesn't understand why this matters or suggests exposing floor_price with encryption

---

## Scoring Summary

| Question | Topic | Max Points |
|----------|-------|------------|
| Q1 | Ontological Placement | 3 |
| Q2 | Extension Pattern | 5 |
| Q3 | Architectural Constraint | 4 |
| Q4 | Asynchronous Communication | 4 |
| Q5 | Security Pattern | 4 |
| **Total** | | **20** |

**Success Thresholds:**
- **Excellent (18-20 points):** >90% comprehension — Claude fully internalized the architecture
- **Good (16-17 points):** 80-89% comprehension — Claude understands core patterns, minor gaps
- **Acceptable (14-15 points):** 70-79% comprehension — Claude grasps ontology, needs pattern refinement
- **Poor (<14 points):** <70% comprehension — Anchor failed, needs revision

---

## A/B Testing Protocol

### Hypothesis

**H0 (Null):** The Architectural Anchor achieves ≥80% comprehension accuracy compared to full documentation, using <25% of the token volume.

**H1 (Alternative):** The Architectural Anchor achieves <80% comprehension accuracy OR requires >25% of documentation tokens.

### Methodology

1. **Test 3 fresh Claude instances** per group (Control, Treatment, Compressed)
2. **Administer all 5 comprehension questions** to each instance
3. **Score responses** using the rubric above
4. **Calculate mean scores** per group:
   - Control Group (Full Docs): Expected ~18-20 points (baseline)
   - Treatment Group (Full Anchor): Expected ~16-18 points (target: >16 = 80%)
   - Compressed Group (600 tokens): Expected ~14-16 points (target: >14 = 70%)

### Token Count Comparison

| Documentation | Token Count (approx) | Compression Ratio |
|---------------|---------------------|-------------------|
| Full docs (control) | ~5000 tokens | 1.0× (baseline) |
| Full anchor (treatment) | ~1250 tokens | 4.0× compression |
| Compressed anchor | ~600 tokens | 8.3× compression |

**Target:** Treatment group achieves >80% of control group accuracy with 4× compression.

### Results Template

```markdown
## Test Results (Date: YYYY-MM-DD)

### Control Group (Full Documentation)
- Instance 1: 19/20 (95%)
- Instance 2: 18/20 (90%)
- Instance 3: 20/20 (100%)
- **Mean:** 19.0/20 (95%) — Baseline

### Treatment Group (Full Anchor ~1250 tokens)
- Instance 1: __/20 (__)
- Instance 2: __/20 (__)
- Instance 3: __/20 (__)
- **Mean:** __/20 (__%) — Target: >16/20 (>80%)

### Compressed Group (Compressed Anchor ~600 tokens)
- Instance 1: __/20 (__)
- Instance 2: __/20 (__)
- Instance 3: __/20 (__)
- **Mean:** __/20 (__%) — Target: >14/20 (>70%)

### Conclusion
- [ ] Hypothesis confirmed (Treatment ≥80% of Control, <25% tokens)
- [ ] Hypothesis rejected (revise anchor)
- Notes: ___
```

---

## Error Analysis Framework

### Common Failure Modes

1. **Ontological Confusion**
   - **Symptom:** Places business logic in Genome or Proteins in Nucleus
   - **Root Cause:** Unclear boundary definitions in anchor
   - **Fix:** Strengthen Layer 2 Semantic Keys with concrete examples

2. **Pattern Misapplication**
   - **Symptom:** Suggests direct imports instead of SkillRegistry dispatch
   - **Root Cause:** Trinity Pattern not emphasized enough
   - **Fix:** Add explicit anti-patterns to Layer 3 Invariant Laws

3. **Metaphor Abandonment**
   - **Symptom:** Uses generic terms like "service layer" instead of "Nucleus"
   - **Root Cause:** Metaphor fatigue or insufficient reinforcement
   - **Fix:** Add reminder in Layer 1 Genetic Hash about metaphor enforcement

4. **Security Blind Spots**
   - **Symptom:** Doesn't recognize Hidden Knowledge importance
   - **Root Cause:** Security patterns buried in wall of text
   - **Fix:** Elevate security invariants to top-level bullets in Layer 3

---

## Iteration Protocol

If anchor fails validation (Mean score <16/20 for Treatment Group):

1. **Analyze error patterns** using Error Analysis Framework
2. **Revise anchor** targeting specific failure modes
3. **Increment version** (HIVE_GENOME_v1 → HIVE_GENOME_v2)
4. **Re-test** with fresh Claude instances
5. **Document changes** in anchor changelog

---

## Real-World Validation Tasks

Beyond comprehension questions, test with practical tasks:

### Task 1: Code Review Simulation
**Scenario:** Present Claude with a PR that violates ontological purity (e.g., Genome importing from Nucleus)

**Expected Behavior:**
- Identifies violation immediately
- Cites ontological purity rule
- Suggests correct pattern (move implementation to Nucleus, keep protocol in Genome)

### Task 2: Feature Implementation
**Scenario:** "Add Slack notifications to the Hive"

**Expected Output:**
1. Identifies as Level 3 Organ (SlackProtein)
2. Outlines Trinity Pattern implementation
3. Shows SkillRegistry registration
4. Demonstrates Connector dispatch via `registry.execute('slack', ...)`

### Task 3: Debugging Assistance
**Scenario:** "NATS events aren't reaching bee-keeper. Where would you investigate?"

**Expected Response:**
1. Checks Generator (G) in core-service (event publication)
2. Checks NATS topic names match subscription patterns
3. Checks Aggregator (A) in bee-keeper (event consumption)
4. Validates Protocol Buffer encoding compatibility

---

## Continuous Validation

**Recommended Cadence:**
- **After major architecture changes:** Re-run full A/B test
- **After anchor revisions:** Test compressed version only
- **Monthly:** Spot-check with 2-3 random comprehension questions

**Metrics Tracking:**
- Maintain running log of validation scores over time
- Track which questions have highest failure rates
- Monitor token count inflation as anchor evolves

---

**For the glory of the Hive. 🐝**
