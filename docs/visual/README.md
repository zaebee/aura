# 📄 `docs/visual/README.md`

```md
# Visual Reasoning Layer

This directory contains **visual blueprints** of Aura Hive reasoning models.

Visual artifacts are intended to improve **human understanding** of how the
hive is interpreted by advisory systems. They are **non-executable** and
**non-authoritative**.
```

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
declarative advisory models defined elsewhere in the repository
(e.g. `imp/imp-001/hive.yaml`).

**Hierarchy of truth:**

1. Declarative advisory model (YAML)
2. Visual blueprints (Mermaid, Markdown)
3. Rendered documentation

---

## Structure

```text
visual/
 ├─ hive/         # Hive-level reasoning blueprints
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
* Visual artifacts SHOULD remain high-level

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