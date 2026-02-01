# 📄 `docs/visual/index.md`

```md
# Aura Hive — Visual Reasoning Index

This section provides a visual overview of Aura Hive
from an **advisory and reasoning perspective**.

The diagrams in this section illustrate how observability signals,
events, and interpretations relate conceptually.
```

---

## Hive-Level Blueprint

```mermaid
flowchart LR
    Services[Services]
    Observability[Metrics / Logs / Traces]
    Advisor[Bee Advisor]
    Operator[Human Operator]

    Services --> Observability
    Observability --> Advisor
    Advisor --> Operator
```

---

## How to Read These Diagrams

* Diagrams describe **interpretation**, not execution
* Arrows indicate **information flow**, not control flow
* No diagram implies automation or authority

These diagrams answer the question:

> *“How does the hive understand itself?”*

---

## Relation to Advisory Model

Visual diagrams are aligned with the declarative advisory model
defined in:

* `imp/imp-001/hive.yaml`
* `docs/standards/STD-001.md`
* `docs/standards/IMP-001.md`

---

## Navigation

* Hive reasoning diagrams → `visual/hive/`
* Advisory pipelines → `visual/pipelines/`
* Component-level views → `visual/components/`

---

## Status

Visual artifacts are **informative**, **optional**, and **non-normative**.