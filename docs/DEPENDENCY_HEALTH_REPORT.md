# Dependency Health Report: StableHacks Sprint

**Generated:** 2026-03-20  
**Status:** ⚠️ ATTENTION REQUIRED

---

## Executive Summary

The Hive's dependency ecosystem is **mostly healthy** but has **2 critical issues** that must be resolved before the hackathon demo:

| Severity | Count | Description |
|----------|-------|-------------|
| 🔴 CRITICAL | 2 | Version mismatches that may cause runtime failures |
| 🟡 WARNING | 4 | Version inconsistencies across packages |
| 🟢 HEALTHY | 15 | Dependencies with consistent versioning |

---

## Critical Issues (Must Fix)

### Issue 1: pytest-asyncio Version Mismatch

**Severity:** 🔴 CRITICAL  
**Files Affected:**
- `core/pyproject.toml` (line 51): `pytest-asyncio>=1.3.0`
- `pyproject.toml` (line 75): `pytest-asyncio>=1.3.0`
- `synapses/telegram-bot/pyproject.toml` (line 26): `pytest-asyncio>=0.23.0` ✅

**Problem:**
```
pytest-asyncio>=1.3.0 (2023-02-20) is SEVERELY OUTDATED
Current stable version: 0.24.0+ (2024)
```

**Impact:**
- `pytest-asyncio 1.3.0` lacks critical bug fixes for Python 3.12
- Some async fixtures may not work correctly
- Potential race conditions in integration tests

**Recommended Fix:**
```toml
# In core/pyproject.toml and pyproject.toml:
pytest-asyncio>=0.24.0,
```

**Note:** The `synapses/telegram-bot/` has the correct version (`>=0.23.0`). The core packages need to catch up.

---

### Issue 2: ruff target-version Inconsistency

**Severity:** 🔴 CRITICAL  
**Files Affected:**
- `pyproject.toml` (line 83): `target-version = "py313"`
- `synapses/mcp-server/pyproject.toml` (line 34): `target-version = "py313"`
- `agents/bee-keeper/pyproject.toml` (line 30): `target-version = "py312"`

**Problem:**
```
All packages declare requires-python = ">=3.12"
But ruff is configured to target py313 (Python 3.13)
```

**Impact:**
- Linter may pass but runtime may fail on Python 3.12
- Some py313-specific syntax may be introduced

**Recommended Fix:**
```toml
# Standardize on py312 (matches requires-python)
[tool.ruff]
target-version = "py312"
```

---

## Warnings (Should Fix)

### Warning 1: OpenTelemetry Instrumentation Versions

**Severity:** 🟡 WARNING  
**Files:** All packages with OpenTelemetry

**Observation:**
```python
opentelemetry-instrumentation-fastapi>=0.45b0  # Beta version
opentelemetry-instrumentation-grpc>=0.45b0    # Beta version
opentelemetry-instrumentation-sqlalchemy>=0.45b0  # Beta version
```

**Impact:**
- Beta versions may have breaking changes
- Some instrumentation may not work correctly

**Recommendation:** Pin to stable releases when available, or accept beta risk for hackathon.

---

### Warning 2: nox/lock File Missing

**Severity:** 🟡 WARNING  
**Observation:** No `uv.lock`, `poetry.lock`, or `pip-lock` file found.

**Impact:**
- Different developers may get different dependency versions
- Reproducibility issues in CI/CD
- Potential "works on my machine" failures

**Recommendation:** Generate lock file before hackathon:
```bash
uv lock
git add uv.lock
```

---

### Warning 3: Workspace Dependency References

**Severity:** 🟡 WARNING  
**Observation:** Several packages reference `aura-core` and `aura-worker` as workspace dependencies.

```toml
# In core/pyproject.toml:
aura-core = { workspace = true }

# In pyproject.toml:
aura-core
aura-worker
```

**Impact:**
- Internal packages must be built/published for this to work
- May fail if packages aren't in the workspace

**Current Status:** ✅ Seems correct with `[tool.uv.workspace]` configuration.

---

### Warning 4: DSPy and LangChain Compatibility

**Severity:** 🟡 WARNING  
**Files:** `pyproject.toml`, `core/pyproject.toml`

**Observation:**
```python
dspy-ai>=2.0.0
langchain-mistralai>=1.1.1
```

**Impact:**
- DSPy and LangChain may have conflicting dependencies
- Both use similar LLM abstractions differently
- Potential import conflicts

**Recommendation:** Test the LLM integration thoroughly before demo.

---

## Healthy Dependencies

### ✅ Core Dependencies (Consistent)

| Dependency | Version | Status |
|------------|---------|--------|
| Python | >=3.12 | ✅ Correct |
| protobuf | >=6.33.5 | ✅ Current |
| grpcio | >=1.76.0 | ✅ Current |
| pydantic | >=2.0.0 | ✅ Current |
| structlog | >=25.0.0 | ✅ Current |
| opentelemetry-api | >=1.24.0 | ✅ Current |
| solana | >=0.34.0 | ✅ Current |
| redis | >=5.0.0 | ✅ Current |

### ✅ Blockchain Dependencies (Healthy)

| Dependency | Version | Notes |
|------------|---------|-------|
| solana | >=0.34.0 | Latest RPC support |
| solders | >=0.21.0 | Keypair handling |
| web3 | >=7.14.1 | Ethereum compatibility |
| eth-account | >=0.13.7 | Wallet management |

### ✅ Observability Stack (Consistent)

| Dependency | Version | Status |
|------------|---------|--------|
| opentelemetry-api | >=1.24.0 | ✅ |
| opentelemetry-sdk | >=1.24.0 | ✅ |
| prometheus-client | >=0.21.1 | ✅ |
| structlog | >=25.0.0 | ✅ |

---

## Dependency Graph

```
aura (root)
├── aura-core (workspace)
│   ├── pydantic>=2.0.0
│   ├── betterproto>=2.0.0b7
│   └── opentelemetry-api>=1.20.0
├── aura-worker (workspace)
│   ├── gradio>=4.0.0
│   └── aura-core
└── core (workspace)
    ├── aura-core
    ├── dspy-ai>=2.0.0  ⚠️
    ├── langchain-mistralai>=1.1.1  ⚠️
    └── pytest-asyncio>=1.3.0  🔴

api-gateway (workspace)
├── aura-core
└── grpcio>=1.76.0

synapses/
├── mcp-server
│   ├── aura-core
│   └── fastmcp==2.12.3
└── telegram-bot
    ├── aura-core
    └── aiogram>=3.17.0

agents/
└── bee-keeper
    ├── aura-core
    └── litellm>=1.63.0
```

---

## Recommendations

### Before Hackathon Demo

1. **Update pytest-asyncio** in `core/` and root `pyproject.toml`:
   ```bash
   # Edit pyproject.toml
   sed -i 's/pytest-asyncio>=1.3.0,/pytest-asyncio>=0.24.0,/' pyproject.toml core/pyproject.toml
   ```

2. **Fix ruff target-version** in all packages:
   ```bash
   # Standardize to py312
   find . -name 'pyproject.toml' -exec sed -i 's/target-version = "py313"/target-version = "py312"/g' {} \;
   ```

3. **Generate lock file**:
   ```bash
   uv lock
   ```

### During Development

- Use `uv sync --group dev` to ensure dev dependencies are installed
- Run `make test` before committing
- If you see import errors, run `buf generate` for proto files

### CI/CD

Add these checks:
```yaml
- name: Check pytest-asyncio version
  run: uv pip show pytest-asyncio | grep Version

- name: Lint check
  run: make lint
```

---

## Appendix: Package Versions Matrix

| Package | Python | protobuf | pytest-asyncio | ruff target |
|---------|--------|----------|----------------|-------------|
| root | >=3.12 | >=6.33.5 | >=1.3.0 🔴 | py313 🔴 |
| core | >=3.12 | >=6.33.5 | >=1.3.0 🔴 | - |
| aura-core | >=3.12 | - | - | - |
| aura-worker | >=3.10 | - | - | - |
| api-gateway | >=3.12 | >=6.33.5 | - | - |
| mcp-server | >=3.12 | - | - | py313 🔴 |
| telegram-bot | >=3.12 | - | >=0.23.0 ✅ | - |
| bee-keeper | >=3.12 | - | - | py312 ✅ |

---

*Report generated by System Integration Chaperone*
*StableHacks Sprint - 2026-03-20*
