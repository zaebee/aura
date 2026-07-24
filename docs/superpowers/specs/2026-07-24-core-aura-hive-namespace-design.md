# Design: core → `aura_hive` namespace refactor

**Date:** 2026-07-24
**Status:** Approved (design), pending implementation plan
**Scope:** Final app in the app-namespace refactor series (#224 mcp-server, #225 bee-keeper, #226 telegram-bot, #227 api-gateway).

## Problem

`core` (the gRPC service) uses a flat `src/` layout with top-level modules/packages
(`config/`, `hive/`, `main.py`, `nats_gateway.py`). When installed or placed on
`PYTHONPATH`, these generic names (`config`, `hive`, `main`) collide with the other
services' modules in a shared environment. `core` is the last service still on the flat
layout, and — unlike the others — it is a **cross-service dependency**: `mcp-server`
embeds the core organism and imports `from config import Settings` and
`from hive.cortex import HiveCell` via `core/src` on `MCP_PATH`.

Goal: wrap core's code in a single `aura_hive` package so imports are namespaced and the
collision is removed, completing the pattern established by the previous four services.

## Package name

`aura_hive` — thematic (the whole project is "the Hive"), distinct from the `aura_core`
library in `packages/aura-core`, and not a generic top-level name. Decided during
brainstorming.

## Target structure

```
core/src/aura_hive/          # new package
    __init__.py
    main.py                  # was core/src/main.py — gRPC entrypoint
    nats_gateway.py          # was core/src/nats_gateway.py
    config/                  # was core/src/config/  (12 modules)
    hive/                    # was core/src/hive/    (8 subpackages:
                             #   proteins, connector, transformer, services,
                             #   membrane, metabolism, generator, aggregator)
```

- Moves done via `git mv` so history is preserved.
- `core/tests/` stays in place; only its import statements change.

## Import rewrites (absolute)

Mechanical, anchored to import lines only:

| From | To |
|------|-----|
| `from config…` / `import config…` | `from aura_hive.config…` / `import aura_hive.config…` |
| `from hive…` / `import hive…` | `from aura_hive.hive…` / `import aura_hive.hive…` |
| `from nats_gateway…` / `import nats_gateway…` | `from aura_hive.nats_gateway…` |

Regex anchor: `^\s*(from|import) (config|hive|nats_gateway)([. ]|$)` — matches only
import statements at line start, safe from false positives (variables, strings).

Scale: ~46 sites in `core/src`, ~66 sites in `core/tests` (≈112 total).

**Style: absolute imports** (`from aura_hive.hive.cortex import …`), not relative.
Rationale: core's `hive/` is deeply nested (`hive/proteins/transaction/…`,
`hive/metabolism/…`); relative imports like `from ...config import` across that depth are
fragile and hard to transform mechanically. Absolute keeps every rewrite a simple prefix.

## Cross-service & entry-point changes (same PR)

These are inseparable from the move — shipping core's move without them breaks
`mcp-server` and the runtime — so they land in one PR:

- **mcp-server** (`synapses/mcp-server/src/aura_mcp/main.py`), 2 lines:
  - `from config import Settings as CoreSettings` → `from aura_hive.config import Settings as CoreSettings`
  - `from hive.cortex import HiveCell` → `from aura_hive.hive.cortex import HiveCell`
- **Makefile** `run-core`: `python -m core.src.main` → `python -m aura_hive.main`.
- **core/Dockerfile**: `CMD ["python", "src/main.py"]` → `CMD ["python", "-m", "aura_hive.main"]`
  (package-relative resolution requires `-m`, not script execution).

**Unchanged:** `CORE_PATH`, `MCP_PATH`, `TOOL_PATH`, and the k8s `values.yaml`
`PYTHONPATH: /app/core/src:/app/core/gen-proto` — all hang off `core/src`, under which
`aura_hive` remains importable. k8s has no command override; the Docker `CMD` is the entry.

## Verification

- `make test` — **core 114 + mcp-server 14** + api-gateway 1 + telegram-bot 6 all green.
  The cross-service pair (core + mcp) is the key regression signal.
- `make lint` — ruff + mypy across all services (mypy's `import-not-found` catches any
  missed or mistyped rewrite).
- **Docker build core** + run the image: `python -m aura_hive.main` must start the gRPC
  server (expected to then fail on DB/NATS connection locally — that failure proves the
  entrypoint and import chain resolved). GHCR login already active for local builds.

## Risks

- **~112 import rewrites** — main risk is a typo or missed site. Caught by `make lint`
  (mypy) + the 128 tests.
- A missed `mcp → core` cross-import → mcp-server's 14 tests go red.
- Single PR by necessity (core + mcp + infra are coupled); larger review surface, but the
  change is mechanical and the test coverage is strong.

## Out of scope

- Renaming the `core` **project** (`[project.name]`, `--package core`, image names) — only
  the Python package layout changes.
- Any behavior change to core logic.
- The two pre-existing run inconsistencies are resolved as a side effect (both entrypoints
  become `python -m aura_hive.main`); no separate work.
