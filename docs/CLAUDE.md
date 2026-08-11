# CLAUDE.md

Guidance for Claude Code (and other agents) working in this repository.

> **This document was rewritten 2026-07-24 to match the ATCG-M architecture the
> code actually uses.** An earlier version described a pre-ATCG-M microservice
> design (`NegotiationService` + pricing-strategy classes in flat `core/src/`);
> those paths and framings are gone. The source of truth for the live structure
> is `tools/distill_knowledge.py` → `docs/knowledge/hive_architecture_v2.json`.

## Project Overview

Aura is a distributed platform for autonomous economic negotiation between AI
agents and service providers. Its architecture is a **biological metaphor**: the
whole system is modelled as a **Hive of cells**, and every unit of computation is
expressed as cellular machinery rather than conventional "services/managers".

The organizing pattern is the **ATCG-M metabolism** (see below). The canonical,
fully-formed cell is the **Core** service; the other services are edge adapters
("synapses"), specialized workers, or auditor agents around it.

## The Living Metaphor — 4-Level Ontology

| Level | Meaning | Where it lives |
|-------|---------|----------------|
| **Genome** | Immutable protocols + shared DNA. Never contains business logic. | `packages/aura-core` (`aura_core`) + generated protobufs (`aura_core_gen`) |
| **Nucleus** | The sovereign brain — a complete cell running the full ATCG-M metabolism. | `core/` → `core/src/aura_hive/` (package `aura_hive`) |
| **Organs** | Proteins — single-purpose skills (enzymes) wired into the Nucleus. | `core/src/aura_hive/hive/proteins/*` |
| **Citizens** | Composed edge entities: synapses (protocol adapters), workers, agents. | `synapses/*`, `api-gateway/`, `agents/*`, `packages/aura-worker` |

**Genome exports** (`from aura_core import ...`): the DNA protocols
`Aggregator, Transformer, Connector, Generator, Membrane, SkillProtocol,
BaseConnector, SkillRegistry, MetabolicLoop`; helpers `make_struct, map_action,
get_raw_key`; and geography `find_hive_root, MACRO_ATCG_FOLDERS,
ALLOWED_CHAMBERS, resolve_brain_path`. **Prefer importing these over
re-implementing them** — several services currently copy `find_hive_root` /
`MetabolicLoop` locally instead (a known drift; see "Honest state").

## The ATCG-M Metabolism

Every cell runs one metabolic cycle per signal. The canonical implementation is
`core/src/aura_hive/hive/metabolism/main.py::MetabolicLoop.execute(signal)`:

```
M(in)  membrane.inspect_inbound(signal)        # guard the incoming signal
A      context     = aggregator.perceive(...)   # A — sense the environment
T      decision    = transformer.think(...)     # T — reason / decide
M(out) membrane.inspect_outbound(decision, ...) # guard the outgoing decision  ← Hidden Knowledge enforced here
C      observation = connector.act(...)         # C — act on the decision
G                    generator.pulse(...)        # G — emit events / heartbeat
```

- **A — Aggregator** (`hive/aggregator/`): perceive/gather context.
- **T — Transformer** (`hive/transformer/`): think/decide. The pricing brains
  (`RuleBasedStrategy` deterministic, `LiteLLMStrategy` LLM-backed) live **inside**
  `hive/transformer/main.py` — selected by config, not a separate service.
- **C — Connector** (`hive/connector/`): act (persistence, external calls).
- **G — Generator** (`hive/generator/`): pulse/emit (events, heartbeats).
- **M — Membrane** (`hive/membrane/`): guards on both boundaries; the outbound
  guard is where the Hidden-Knowledge invariant is enforced.
- **Cortex** (`hive/cortex.py::HiveCell`): assembles the cell — wires the proteins
  into a `SkillRegistry` and builds the organism (`build_organism()`).

**Organ Proteins** (`hive/proteins/`): `blockchain_data` (GoldRush), `coherence`,
`discovery`, `guard`, `kinetic`, `perception`, `persistence`, `pulse` (NATS),
`reasoning` (embeddings/LLM), `telemetry`, `transaction` (Solana).

## Core Patterns & Invariants

The self-model (`distill`) declares **6 hard invariants**. Honor them:

1. **Trinity pattern** — every protein implements `bind(settings, provider)` →
   `async initialize() -> bool` → `async execute(...) -> Observation`. Wired by
   the Cortex; never call protein internals directly.
2. **Hidden Knowledge** — `floor_price` (and internal thresholds) must NEVER reach
   an agent/client. Enforced by `Membrane.inspect_outbound`. Agents only ever see
   `accepted / countered / rejected / ui_required`.
3. **Cellular metaphor** — biological names (Genome, Nucleus, Protein, Membrane,
   Bloodstream). `Manager/Service/Helper/Util/Controller/Adapter` are "heresy".
4. **Ontological purity** — depend only downward on the Genome
   (`from aura_core.dna import ...`); the Genome must never import service code.
5. **Fractal completeness** — a full cell has all nucleotides
   (`aggregator, transformer, connector, generator, membrane` + `cortex, metabolism`).
6. **Contract-first APIs** — change `proto/aura/**`, run `buf generate`, then update
   implementations. Never hand-edit generated code (`*/gen-proto/`, `aura_core_gen`).

## Services Map

| Service | Package | Role | Entry |
|---------|---------|------|-------|
| **core** | `aura_hive` | The Nucleus — full ATCG-M cell; gRPC (grpclib) on `:50051`. `NegotiationService` delegates to `MetabolicLoop`. | `python -m aura_hive.main` |
| **api-gateway** | `api_gateway` | Synapse — HTTP/JSON edge (FastAPI); signature verification, rate-limit; forwards to core. | `uvicorn api_gateway.main:app` (`:8000`) |
| **telegram-bot** | `telegram_bot` | Synapse — Telegram receptor/translator/effector; talks to the Hive over NATS. | `python -m telegram_bot.main` |
| **mcp-server** | `aura_mcp` | Synapse — MCP adapter (fastmcp 3.x); embeds a `HiveCell`. | `python -m aura_mcp.main` |
| **bee-keeper** | `aura_keeper` | Citizen agent — audits the Hive's architecture (partial cell). | `python -m aura_keeper.main` |
| **aura-worker** | `aura_worker` | Citizen — remote Jupyter/Colab vision worker (Ollama + gradio); frpc tunnel. | (Colab / worker node) |

Synapses use a **`receptor → translator → effector`** shape — a lightweight
mini-metabolism with the ATCG-M mapping **receptor = A, translator = T,
effector = C·G**. This is now stated explicitly in each synapse module's
docstring and in `docs/ontology/patterns.yaml` (`synapse_pattern`). Applies to
the NATS/MCP synapses (`telegram-bot`, `mcp-server`); `api-gateway` is an HTTP
edge with a different shape.

## Development Commands

Uses **`uv`** (not pip/poetry) and **`buf`** for protos. All Python is a single uv
workspace; only the **root `uv.lock`** is authoritative (member locks were removed).

```bash
uv sync --group dev          # install dev deps
make generate                # buf generate → gen-proto (run after editing proto/)
make lint                    # ruff + mypy (all services) + bandit + buf lint
make test                    # full suite (see below)
make format                  # ruff format
make run-core                # python -m aura_hive.main
make run-gateway             # uvicorn api_gateway.main:app
```

## Testing

`make test` runs each service's suite on its own `PYTHONPATH` (188 tests total):

- **core** (114): `PYTHONPATH=$(CORE_PATH) pytest core/tests/`
- **api-gateway** (1): env supplied by `api-gateway/tests/conftest.py`
- **telegram-bot** (6): isolated `TG_PATH`
- **mcp-server** (14): needs fastmcp → `uv sync --package aura-mcp --inexact` first
- **aura-worker** (53): needs gradio → `uv sync --package aura-worker --inexact` (the
  `ml`/torch group is intentionally NOT synced)

Tests mock heavy deps (NATS, httpx, subprocess, torch/gradio) — no live services
required. Per-service config uses pydantic-settings with `env_prefix` (`AURA_` for
core, `AURA_GATEWAY__` for api-gateway) and nested `__` delimiter.

## Self-Model (the Hive's own map)

`make tools-distill` scans the codebase and emits
`docs/knowledge/hive_architecture_v2.{bin,json}` — the Genome/Nucleus/Organs/
Citizens/invariants extracted from the actual code. Run it to get the current,
authoritative structural snapshot. `bee-keeper` audits these invariants.

## Honest state (drift to be aware of)

The ATCG-M pattern is **fully realized only in `core`**. Around it:

- **Docs lagged the code** by a paradigm (this file's rewrite closes that gap).
- **Naming heresy persists** in real symbols: `NegotiationService`, `MarketService`,
  `WorkerController`, `NatsAdapter`, `GrpcAdapter` — against invariant #3.
- **Fractal-by-copy-paste**: `find_hive_root` (and similar) are re-implemented per
  service instead of imported from the Genome, which already exports them.
- **Partial cells**: `bee-keeper`, `bee-evolver`, and even `frontend` each carry a
  *different subset* of nucleotides (usually missing `membrane`); synapses have none.
- **God-proteins**: `PersistenceSkill` / `TransactionSkill` have accreted many
  responsibilities — drifting from "one enzyme, one reaction".

When adding code, push toward the invariants (import the Genome, keep proteins
single-purpose, use biological names) rather than reinforcing the drift.

## betterproto: absence is not `None`

Generated messages (`aura_core_gen`) use betterproto, whose treatment of unset
fields catches everyone — one real bug and four false alarms in a single
afternoon of reviews. **Three kinds of field behave three different ways, and
the two obvious tests for absence disagree with each other.**

Verified against this workspace **with `aura_core` imported**, which matters:
`aura_core.struct_utils` patches `Message.__getattribute__` at import time, so
one of the behaviours below is ours rather than the library's (see the oneof
rule). A probe whose imports do not match the code it stands in for will report
something the application does not do. Re-check after a betterproto upgrade.

```python
Observation().metadata is None    # False — default-constructed on ACCESS
bool(Observation().metadata)      # False — Message defines __bool__
Observation(metadata=None).metadata is None   # True — explicit None really is None
```

| what you write | what happens |
|---|---|
| `if msg.field is not None:` | **always true** for a message field — dead code |
| `if msg.field:` | works: an all-default message is falsy |
| `msg.field.to_dict()` | safe unless someone passed `field=None` explicitly |

**Rules of thumb:**

- **Test absence by value, never by identity.** An identity check on a message
  field never fires, and the failure is silent — in #265 every receipt-less
  response rendered a JSON object full of empty strings because
  `if receipt is None` was dead code.

  `if not receipt:` is the concise safe form: falsy for a default-constructed
  message *and* for an explicit `None`. Use `if not receipt.version:` when the
  question is "is this well-formed" rather than "is there anything here" — but
  note it raises on an explicit `None`, so the belt-and-braces version is
  `if receipt is None or not receipt.version:`.
- **Oneof members are `None` when inactive — but only because we patch them.**
  Stock betterproto raises `AttributeError` naming the member that *is* set.
  `aura_core.struct_utils` replaces `Message.__getattribute__` at import time so
  inactive members return `None` instead, because betterproto's own `dump()`
  compares nested messages with `==`, and the dataclass `__eq__` touches every
  field — including inactive oneof members — which made serialisation raise.

  ```python
  # with aura_core imported, i.e. every real code path
  Intent().negotiation          # None
  # without it — a bare script, an isolated test
  Intent().negotiation          # AttributeError: 'params' is set to None, not 'negotiation'
  ```

  So `if intent.negotiation:` works in the application and may not in a probe
  you write to check something. **`betterproto.which_one_of()` is unaffected by
  the patch and is the read that behaves the same either way** — prefer it, and
  be suspicious of any experiment whose imports do not match the code it is
  standing in for.

- **A truthiness check is not a value check.** `bool(receipt.signature)` is
  `False` for an unset signature but `True` for one carrying a scheme and no
  signature. If the field has a load-bearing member, check that member.
- Guarding a `.to_dict()` against `None` is defensible on a shared helper, but
  say in a comment that it cannot currently fire — otherwise the next reader
  takes it for a fix to a live fault.

## Important Notes

- Python **3.12+**, package manager **`uv`**.
- gRPC uses **grpclib** (async), not grpcio, in core.
- Never edit generated protobuf code (`*/gen-proto/`, `aura_core_gen`); regenerate.
- Compose file is `compose.yml`; k8s/Helm live under `deploy/aura/`.
- The optional geography config `hive-manifest.yaml` (repo root; k8s configmap at
  `/app/hive-manifest.yaml`) feeds the Membrane's folder/chamber rules — absent →
  safe empty defaults.
