# core → `aura_hive` Namespace Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the `core` gRPC service's flat `src/` layout in an `aura_hive` package, rewrite all internal + test + cross-service imports to absolute `aura_hive.*`, and update the two entrypoints — completing the app-namespace refactor series.

**Architecture:** Pure mechanical refactor. `core/src/{config,hive,main.py,nats_gateway.py,__init__.py}` move into `core/src/aura_hive/`. All `from config…`/`from hive…`/`from nats_gateway…` imports across `core/src`, `core/tests`, and the one cross-service consumer (`mcp-server`) gain the `aura_hive.` prefix. Verified by the existing 128-test suite + `make lint` + a core Docker build. No behavior change.

**Tech Stack:** Python 3.12, `uv` workspace, hatchling/setuptools, `make` targets (`lint`, `test`), Docker, betterproto/grpc.

## Global Constraints

- Package name is exactly `aura_hive` (verbatim; not `aura-hive`, not `core`).
- Imports are **absolute** (`from aura_hive.hive.cortex import …`), never relative — core's `hive/` nests too deeply for relative imports to be safe.
- Do **not** rename the `core` project: `[project.name] = "core"`, `--package core`, and the `aura-core` image name stay as-is. Only the Python package layout changes.
- No logic changes to core; the diff is moves + import prefixes + two entrypoint strings.
- Move files with `git mv` (preserve history).
- Branch: `refactor/core-namespace` (already created off `origin/main`).
- Docker builds pull `ghcr.io/astral-sh/uv` — GHCR login is required: `gh auth token | docker login ghcr.io -u zaebee --password-stdin`.
- Regex anchor for import rewrites (line-start imports only, avoids false positives): `^\s*(from|import) (config|hive|nats_gateway)([. ]|$)`.

---

### Task 1: Move core into the `aura_hive` package and rewrite all imports

The package move and every import rewrite (core/src, core/tests, and mcp-server) are one atomic unit — a half-moved package fails every test. This task ends when `make test` and `make lint` are both green.

**Files:**
- Move: `core/src/{__init__.py, main.py, nats_gateway.py}` → `core/src/aura_hive/`
- Move: `core/src/config/` → `core/src/aura_hive/config/`
- Move: `core/src/hive/` → `core/src/aura_hive/hive/`
- Modify (imports): every `.py` under `core/src/aura_hive/` (~46 sites)
- Modify (imports): every `.py` under `core/tests/` (~66 sites)
- Modify: `synapses/mcp-server/src/aura_mcp/main.py` (2 sites)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the importable package `aura_hive` with `aura_hive.main`, `aura_hive.config` (submodules `server`, `crypto`, `database`, `perception`, …), `aura_hive.hive.cortex.HiveCell`, `aura_hive.hive.metabolism.MetabolicLoop`, `aura_hive.nats_gateway.NatsSignalGateway`. mcp-server's `aura_mcp.main` consumes `from aura_hive.config import Settings` and `from aura_hive.hive.cortex import HiveCell`.

- [ ] **Step 1: Move the modules into the package**

```bash
cd core/src
mkdir -p aura_hive
for f in __init__.py main.py nats_gateway.py config hive; do git mv "$f" "aura_hive/$f"; done
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
cd ../..
git status --short core/src | head
```
Expected: `R  core/src/main.py -> core/src/aura_hive/main.py` (and similar renames for the others).

- [ ] **Step 2: Rewrite imports inside `core/src/aura_hive`**

```bash
grep -rlE '^\s*(from|import) (config|hive|nats_gateway)([. ]|$)' core/src/aura_hive --include='*.py' | while read f; do
  sed -i -E 's/^(\s*)from (config|hive|nats_gateway)([. ])/\1from aura_hive.\2\3/' "$f"
  sed -i -E 's/^(\s*)import (config|hive|nats_gateway)([. ]|$)/\1import aura_hive.\2\3/' "$f"
done
echo "=== any bare config/hive/nats_gateway imports left? ==="
grep -rnE '^\s*(from|import) (config|hive|nats_gateway)([. ]|$)' core/src/aura_hive --include='*.py' || echo "  none ✓"
```
Expected: `none ✓`.

- [ ] **Step 3: Rewrite imports inside `core/tests`**

```bash
grep -rlE '^\s*(from|import) (config|hive|nats_gateway)([. ]|$)' core/tests --include='*.py' | while read f; do
  sed -i -E 's/^(\s*)from (config|hive|nats_gateway)([. ])/\1from aura_hive.\2\3/' "$f"
  sed -i -E 's/^(\s*)import (config|hive|nats_gateway)([. ]|$)/\1import aura_hive.\2\3/' "$f"
done
grep -rnE '^\s*(from|import) (config|hive|nats_gateway)([. ]|$)' core/tests --include='*.py' || echo "  none ✓"
```
Expected: `none ✓`.

- [ ] **Step 4: Rewrite mcp-server's 2 cross-service imports**

```bash
sed -i -E 's/^from config import/from aura_hive.config import/; s/^from hive\.cortex import/from aura_hive.hive.cortex import/' \
  synapses/mcp-server/src/aura_mcp/main.py
grep -nE 'aura_hive' synapses/mcp-server/src/aura_mcp/main.py
```
Expected: two lines — `from aura_hive.config import Settings as CoreSettings` and `from aura_hive.hive.cortex import HiveCell`.

- [ ] **Step 5: Auto-fix import ordering (ruff will otherwise flag I001)**

```bash
DNA=packages/aura-core/src:packages/aura-core/gen-proto
PYTHONPATH=core/src:core/gen-proto:$DNA uv run --no-sync ruff check --fix core/src core/tests
PYTHONPATH=synapses/mcp-server/src:core/src:$DNA uv run --no-sync ruff check --fix synapses/mcp-server/src/aura_mcp/main.py
```
Expected: `Found N errors (N fixed, 0 remaining)` or `All checks passed!`.

- [ ] **Step 6: Run the full test suite**

```bash
uv sync --group dev >/dev/null 2>&1
export AURA_DATABASE__URL="postgresql://test:test@localhost:5432/test_db" \
       AURA_DATABASE__REDIS_URL="redis://localhost:6379/0" \
       AURA_LLM__API_KEY="test-key-for-ci"
make test 2>&1 | grep -E '=====.*(passed|failed)'
```
Expected: four green lines — `114 passed …` (core), `1 passed …` (api-gateway), `6 passed …` (telegram-bot), `14 passed …` (mcp-server). Any failure ⇒ a missed/mistyped import; re-check Steps 2–4.

- [ ] **Step 7: Run the linter**

```bash
make lint 2>&1 | tail -3
```
Expected: no `error:` lines; final command exit 0. (mypy `import-not-found` here means a rewrite was missed — fix and re-run.)

- [ ] **Step 8: Commit**

```bash
git add -A core synapses/mcp-server
git commit -m "$(cat <<'MSG'
refactor(core): move flat src into aura_hive package

Final app in the namespace refactor. core's flat src/ (config, hive, main,
nats_gateway) is wrapped in an aura_hive package; ~112 internal + test imports
rewritten to absolute aura_hive.*, and the sole cross-service consumer
(mcp-server, 2 lines) updated in lockstep. CORE_PATH/MCP_PATH unchanged
(aura_hive resolves under core/src). Verified: make test green (core 114,
mcp-server 14, api-gateway 1, telegram-bot 6); make lint clean.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: Update the two entrypoints and verify the Docker build

**Files:**
- Modify: `Makefile` (the `run-core` recipe)
- Modify: `core/Dockerfile` (the `CMD` line)

**Interfaces:**
- Consumes: the `aura_hive` package from Task 1 (`aura_hive.main` module with the gRPC server entry).
- Produces: runnable entrypoints `python -m aura_hive.main` (both `make run-core` and the core image `CMD`).

- [ ] **Step 1: Point `make run-core` at the package module**

Edit `Makefile` — in the `run-core` recipe, replace `python -m core.src.main` with `python -m aura_hive.main`:

```makefile
run-core: $(PROTO_SENTINEL)
	# Run Core gRPC service
	PYTHONPATH=$(TOOL_PATH) uv run python -m aura_hive.main
```

- [ ] **Step 2: Point the core image CMD at the package module**

Edit `core/Dockerfile` — replace the final line:

```dockerfile
CMD ["python", "-m", "aura_hive.main"]
```
(was `CMD ["python", "src/main.py"]`; `WORKDIR /app/core` and `ENV PYTHONPATH=/app/core/src:/app/core/gen-proto` stay unchanged — `-m aura_hive.main` resolves under `src`).

- [ ] **Step 3: Log in to GHCR and build the core image**

```bash
gh auth token | docker login ghcr.io -u zaebee --password-stdin
docker build -t aura-core-test -f core/Dockerfile . 2>&1 | grep -iE 'uv sync|Installed|error|denied|writing image|naming to'
docker inspect aura-core-test --format 'CMD={{.Config.Cmd}}'
```
Expected: `Installed … packages`, `writing image …`, `naming to …`, and `CMD=[python -m aura_hive.main]`. No `denied`/`error`.

- [ ] **Step 4: Smoke-run the image (entrypoint + imports resolve)**

```bash
timeout 12 docker run --rm aura-core-test 2>&1 | grep -viE 'Transient|Failed to export|jaeger' | head -6 || true
docker rmi -f aura-core-test >/dev/null 2>&1; true
```
Expected: a startup log line (e.g. gRPC server starting), then a DB/NATS connection error — **not** `ModuleNotFoundError`/`ImportError`. A connection failure proves the entry + import chain resolved; an ImportError means the package move or CMD is wrong.

- [ ] **Step 5: Commit**

```bash
git add Makefile core/Dockerfile
git commit -m "$(cat <<'MSG'
refactor(core): point run-core and Docker CMD at aura_hive.main

Both entrypoints now use `python -m aura_hive.main` (package-relative imports
require -m, not script execution). PYTHONPATH/WORKDIR unchanged. Verified: core
Docker image builds and the container starts (fails only at DB/NATS connect).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: Push, open PR, and confirm CI

**Files:** none (VCS/CI only).

**Interfaces:**
- Consumes: the two commits from Tasks 1–2.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin refactor/core-namespace
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --base main --head refactor/core-namespace \
  --title "refactor(core): move flat src into aura_hive package" \
  --body "Final app in the namespace refactor (after #224 mcp-server, #225 bee-keeper, #226 telegram-bot, #227 api-gateway). Wraps core's flat src/ (config, hive, main, nats_gateway) in an aura_hive package; ~112 internal + test imports rewritten to absolute aura_hive.*, mcp-server's 2 cross-service imports updated in lockstep, run-core + Docker CMD → python -m aura_hive.main. CORE_PATH/MCP_PATH/k8s PYTHONPATH unchanged. Verified locally: make test (core 114, mcp-server 14, api-gateway 1, telegram-bot 6), make lint, core Docker build + container start. Spec: docs/superpowers/specs/2026-07-24-core-aura-hive-namespace-design.md."
```

- [ ] **Step 3: Watch CI to completion**

```bash
RUN=$(sleep 8; gh run list --branch refactor/core-namespace --workflow "Aura Factory" --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" --exit-status
gh run view "$RUN" --json conclusion,jobs -q '"conclusion: \(.conclusion)", (.jobs[] | "  \(.name) = \(.conclusion // .status)")'
```
Expected: `conclusion: success`, with `quality` (runs make lint + make test) and all four `build-and-push` jobs green. A transient `unknown blob` push failure on a build-and-push job is a known GHCR flake — re-run failed jobs with `gh run rerun "$RUN" --failed` and re-watch.

- [ ] **Step 4: Merge and clean up (after green CI)**

```bash
gh pr merge refactor/core-namespace --merge
git push origin --delete refactor/core-namespace
```
Expected: PR state `MERGED`; branch deleted.

---

## Notes for the executor

- The `config/` directory is a package (submodules `server`, `crypto`, `database`, `perception`, `policy`, `llm`, `logic`, `discovery`, `heartbeat`, `kinetic`, `blockchain_data`), so imports like `from config.server import …` become `from aura_hive.config.server import …` — the sed handles this via the `([. ])` group.
- `core/tests` may reference deep paths like `from hive.proteins.transaction.solana_engine import …` → `from aura_hive.hive.proteins.transaction.solana_engine import …`. Same sed.
- If `make test`'s mcp-server step reports `No module named 'fastmcp'`, run `uv sync --package aura-mcp --inexact` first — but the `make test` target already does this; only relevant if running the mcp suite by hand.
