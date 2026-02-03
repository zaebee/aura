# Visual Reasoning Layer

This directory contains **visual Hive Maps** of Aura Hive reasoning models.

Visual artifacts are intended to improve **human understanding** of how the
hive is interpreted by advisory systems. They are **non-executable** and
**non-authoritative**.

---

## Purpose

The visual layer exists to:
- explain architectural and reasoning intent
- provide onboarding and review artifacts
- support discussion and design alignment

Visual documents **do not** define runtime behavior.

---

## Canonical Source of Truth

All visual artifacts are derived from or aligned with
the canonical architecture defined in `docs/FOUNDATION.md`,
`packages/aura-core/src/aura_core/dna.py`, and operational state
in `HIVE_STATE.md`.

**Hierarchy of truth:**

1. Implemented architecture (FOUNDATION.md, dna.py Protocols, operational code)
2. Visual Hive Maps (Mermaid, Markdown)
3. Rendered documentation

---

## Structure

```text
visual/
 ├─ hive/         # Hive-level reasoning maps
 ├─ pipelines/    # Advisory and observability flows
 ├─ components/   # Optional component-focused views
 └─ index.md      # Visual entry point
```

---

## Formats

Supported formats include:

* Mermaid (`.mmd`) for diagrams
* Markdown (`.md`) for explanatory context

Additional formats MAY be introduced if they remain static and readable.

---

## Constraints

* Visual artifacts MUST NOT be used for automation
* Visual artifacts MUST NOT introduce new semantics
* Visual artifacts SHOULD declare their **diagram abstraction level** (distinct from the Four Ontological Levels in FOUNDATION.md):
  - **Organism View:** Full Bee service boundaries and inter-service communication
  - **Cellular View:** ATCG-M nucleotide interactions within a single Bee
  - **Molecular View:** Protocol/interface contracts (gRPC, SkillProtocol)
  - **Ecosystem View:** Multi-bee choreography and event flows

---

## Audience

This layer is intended for:

* operators
* architects
* contributors
* reviewers

It is not intended for machines or deployment tooling.

---

## Status

This layer is **informative** and **experimental**.
