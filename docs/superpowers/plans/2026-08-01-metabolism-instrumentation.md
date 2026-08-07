# Metabolism Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record `{prompt_tokens, completion_tokens, usd, wall_clock}` for every `bee.Keeper` and `bee.Evolver` cycle, durably and append-only, without changing what either bee decides.

**Architecture:** The Transformer returns usage as data; `metabolism.execute()` times the cycle and, in a `finally` block, calls a **Connector** method that appends one JSON line to a log file. A workflow step uploads that file as an artifact; a separate workflow aggregates artifacts and commits them. Collection never writes to the repo, so the instrument cannot perturb the system it measures.

**Tech Stack:** Python 3.12, `pydantic-settings`, `structlog`, `litellm`, `pytest`, GitHub Actions.

## Global Constraints

- Work in the worktree `~/projects/aura/.claude/worktrees/metabolism`, branch `feat/metabolism-instrumentation`, based on `origin/main` @ `9d4f733`. Do not touch the main `~/projects/aura` checkout — it has unrelated uncommitted work.
- **Never use raw `os.getenv` / `os.environ`.** `bee.Keeper`'s own deterministic auditor flags it in diffs, and `FOUNDATIONS.md` §3 mandates `pydantic-settings` with the `AURA_SECTION__VAR` convention. All new configuration goes through each bee's `Settings` class.
- **Never use `print()`.** Same auditor. Use `structlog`.
- **No `subprocess` in new code.** Write-side `subprocess` outside the Connector is the exact boundary violation this instrumentation exists to help detect. `git_sha` comes from the `GITHUB_SHA` environment variable via Settings.
- **Unknown numeric values are `None`, never `0`.** Writing `0` for absent usage turns a paid cycle into a free one and biases any later median downward.
- **`bee.Evolver` must not depend on `aura-core`.** It was deliberately removed in `229298b` to fix CI runtime. The record model and writer are duplicated per bee rather than shared.
- Path asymmetry: `bee-keeper/src/aura_keeper/hive/...` vs `bee-evolver/src/hive/...`.
- Every task ends with a commit. Conventional-commit titles (`feat:`, `test:`, `ci:`).

---

### Task 1: Evolver record model + writer

**Files:**
- Create: `agents/bee-evolver/src/hive/records.py`
- Create: `agents/bee-evolver/tests/test_records.py`
- Modify: `agents/bee-evolver/src/config.py` (add `metabolism_log`, `git_sha`, `dry_run`)
- Modify: `agents/bee-evolver/pyproject.toml` (add pytest dev group)
- Modify: `agents/bee-evolver/src/hive/connector/__init__.py` (add writer method)

**Interfaces:**
- Produces: `MetabolicRecord` dataclass with `to_json_line() -> str`; `EvolverConnector.write_metabolic_record(record: MetabolicRecord) -> None`; `EvolverSettings.metabolism_log: str`, `.git_sha: str`, `.dry_run: bool`.

- [ ] **Step 1: Add the pytest dev group**

In `agents/bee-evolver/pyproject.toml`, after the `[project]` block:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the failing test**

Create `agents/bee-evolver/tests/test_records.py`:

```python
import json

from hive.records import MetabolicRecord


def _record(**overrides) -> MetabolicRecord:
    base = dict(
        ts="2026-08-01T18:40:12Z",
        bee="evolver",
        cycle_id="20260801-184012",
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=1,
        prompt_tokens=3412,
        completion_tokens=688,
        usd=0.0141,
        wall_clock_s=47.3,
        outcome="success",
        dry_run=False,
        proposals=3,
        applied=2,
    )
    base.update(overrides)
    return MetabolicRecord(**base)


def test_to_json_line_is_one_line_of_valid_json():
    line = _record().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    parsed = json.loads(line)
    assert parsed["bee"] == "evolver"
    assert parsed["prompt_tokens"] == 3412


def test_unknown_usage_serialises_as_null_not_zero():
    line = _record(prompt_tokens=None, completion_tokens=None, usd=None).to_json_line()
    parsed = json.loads(line)
    assert parsed["prompt_tokens"] is None
    assert parsed["completion_tokens"] is None
    assert parsed["usd"] is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_records.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hive.records'`

- [ ] **Step 4: Write the record model**

Create `agents/bee-evolver/src/hive/records.py`:

```python
"""Per-cycle metabolic record — one JSONL line per metabolic cycle."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

Outcome = Literal["success", "llm_error", "generator_error", "connector_error"]


@dataclass
class MetabolicRecord:
    """One cycle's cost. Unknown numeric fields are None, never 0."""

    ts: str
    bee: str
    cycle_id: str
    git_sha: str
    model: str | None
    llm_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    usd: float | None
    wall_clock_s: float
    outcome: Outcome
    dry_run: bool
    proposals: int | None = None
    applied: int | None = None

    def to_json_line(self) -> str:
        """Serialise to a single newline-terminated JSON line."""
        return json.dumps(asdict(self), sort_keys=True) + "\n"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_records.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Add settings fields**

In `agents/bee-evolver/src/config.py`, after the `issue_body_limit` field:

```python
    # Metabolism instrumentation (Gate 0)
    metabolism_log: str = Field(
        ".hive/metabolism.jsonl", alias="AURA_METABOLISM_LOG"
    )
    git_sha: str = Field("", alias="GITHUB_SHA")
    # When true the Connector opens no Issues/PRs and sends no Telegram pulse.
    dry_run: bool = Field(False, alias="EVOLVER_DRY_RUN")
```

- [ ] **Step 7: Write the failing writer test**

Create `agents/bee-evolver/tests/test_metabolism_writer.py`:

```python
import json

from config import EvolverSettings
from hive.connector import EvolverConnector
from hive.records import MetabolicRecord


def _settings(tmp_path, **overrides) -> EvolverSettings:
    values = dict(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        AURA_METABOLISM_LOG=str(tmp_path / "nested" / "metabolism.jsonl"),
    )
    values.update(overrides)
    return EvolverSettings(**values)


def _record(cycle_id: str) -> MetabolicRecord:
    return MetabolicRecord(
        ts="2026-08-01T18:40:12Z",
        bee="evolver",
        cycle_id=cycle_id,
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=1,
        prompt_tokens=10,
        completion_tokens=5,
        usd=0.001,
        wall_clock_s=1.0,
        outcome="success",
        dry_run=True,
    )


def test_writer_appends_and_creates_parent_dir(tmp_path):
    settings = _settings(tmp_path)
    connector = EvolverConnector(settings)

    connector.write_metabolic_record(_record("cycle-1"))
    connector.write_metabolic_record(_record("cycle-2"))

    lines = open(settings.metabolism_log, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["cycle_id"] == "cycle-1"
    assert json.loads(lines[1])["cycle_id"] == "cycle-2"


def test_writer_failure_does_not_propagate(tmp_path):
    # A directory where the log file should be makes the open() fail.
    bad = tmp_path / "blocked"
    bad.mkdir()
    settings = _settings(tmp_path, AURA_METABOLISM_LOG=str(bad))
    connector = EvolverConnector(settings)

    connector.write_metabolic_record(_record("cycle-1"))  # must not raise
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_metabolism_writer.py -v`
Expected: FAIL with `AttributeError: 'EvolverConnector' object has no attribute 'write_metabolic_record'`

- [ ] **Step 9: Implement the writer**

In `agents/bee-evolver/src/hive/connector/__init__.py`, add to the imports:

```python
from pathlib import Path

from ..records import MetabolicRecord
```

and add this method to `EvolverConnector`, immediately after `__init__`:

```python
    def write_metabolic_record(self, record: MetabolicRecord) -> None:
        """Append one metabolic record. Never raises — an instrument that
        crashes the organism is worse than no instrument."""
        path = Path(self.settings.metabolism_log)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record.to_json_line())
        except Exception as e:  # noqa: BLE001 - deliberate: see docstring
            logger.warning(
                "metabolism_write_failed", error=str(e), path=str(path)
            )
```

- [ ] **Step 10: Run all evolver tests**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/ -v`
Expected: PASS (4 tests)

- [ ] **Step 11: Commit**

```bash
git add agents/bee-evolver/src/hive/records.py \
        agents/bee-evolver/src/hive/connector/__init__.py \
        agents/bee-evolver/src/config.py \
        agents/bee-evolver/pyproject.toml \
        agents/bee-evolver/tests/
git commit -m "feat(evolver): add metabolic record model and append-only writer"
```

---

### Task 2: Evolver usage capture

**Files:**
- Modify: `agents/bee-evolver/src/hive/models.py` (extend `EvolutionPlan`)
- Modify: `agents/bee-evolver/src/hive/transformer/__init__.py`
- Create: `agents/bee-evolver/tests/test_usage_capture.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `EvolutionPlan.prompt_tokens: int | None`, `.completion_tokens: int | None`, `.usd: float | None`, `.model_used: str | None`, `.llm_calls: int`, `.llm_failed: bool`; module functions `extract_usage(response) -> tuple[int | None, int | None]` and `extract_cost(response) -> float | None` in `hive/transformer/__init__.py`.

- [ ] **Step 1: Extend the plan model**

In `agents/bee-evolver/src/hive/models.py`, replace the `EvolutionPlan` dataclass with:

```python
@dataclass
class EvolutionPlan:
    """Output of the Transformer: ordered list of improvements + metabolic summary."""

    improvements: list[Improvement] = field(default_factory=list)
    # Short narrative for Telegram pulse
    narrative: str = ""
    token_usage: int = 0
    # True if the LLM determined no improvements are needed
    hive_is_optimal: bool = False
    # Metabolism instrumentation (Gate 0). None means "unknown", never 0.
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    usd: float | None = None
    model_used: str | None = None
    llm_calls: int = 0
    llm_failed: bool = False
```

- [ ] **Step 2: Write the failing test**

Create `agents/bee-evolver/tests/test_usage_capture.py`:

```python
from types import SimpleNamespace

from hive.transformer import extract_cost, extract_usage


def test_extract_usage_reads_the_split():
    response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    )
    assert extract_usage(response) == (100, 20)


def test_extract_usage_returns_none_when_usage_absent():
    assert extract_usage(SimpleNamespace()) == (None, None)


def test_extract_usage_returns_none_when_usage_is_falsy():
    assert extract_usage(SimpleNamespace(usage=None)) == (None, None)


def test_extract_usage_returns_none_for_missing_fields_not_zero():
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100))
    prompt, completion = extract_usage(response)
    assert prompt == 100
    assert completion is None


def test_extract_cost_returns_none_when_pricing_fails():
    # An object litellm cannot price must yield None, not 0.0.
    assert extract_cost(SimpleNamespace()) is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_usage_capture.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_usage'`

- [ ] **Step 4: Implement the extractors**

In `agents/bee-evolver/src/hive/transformer/__init__.py`, add after the `logger = ...` line:

```python
def extract_usage(response: Any) -> tuple[int | None, int | None]:
    """Return (prompt_tokens, completion_tokens). None means unknown — never 0,
    because a zero would turn a paid cycle into a free one in the record."""
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


def extract_cost(response: Any) -> float | None:
    """USD for this call, or None when the model cannot be priced."""
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception as e:  # noqa: BLE001 - unpriceable models are expected
        logger.debug("completion_cost_unavailable", error=str(e))
        return None
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_usage_capture.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Populate the plan in `_call_llm`**

In `agents/bee-evolver/src/hive/transformer/__init__.py`, inside `_call_llm`, replace:

```python
        content = response.choices[0].message.content or "{}"
        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = getattr(response.usage, "total_tokens", 0)
```

with:

```python
        content = response.choices[0].message.content or "{}"
        tokens = 0
        if hasattr(response, "usage") and response.usage:
            tokens = getattr(response.usage, "total_tokens", 0)
        prompt_tokens, completion_tokens = extract_usage(response)
        usd = extract_cost(response)
```

and replace the `plan = EvolutionPlan(...)` construction with:

```python
        plan = EvolutionPlan(
            improvements=improvements,
            narrative=data.get("narrative", ""),
            token_usage=tokens,
            hive_is_optimal=bool(data.get("hive_is_optimal", False)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usd=usd,
            model_used=model,
            llm_calls=1,
        )
```

- [ ] **Step 7: Mark the total-failure path**

In `think()`, replace the inner `return EvolutionPlan(...)` in the fallback-failure branch with:

```python
                return EvolutionPlan(
                    narrative=(
                        "The Evolver's brain is offline. "
                        f"Primary: {e}. Fallback: {fe}"
                    ),
                    token_usage=0,
                    llm_failed=True,
                )
```

- [ ] **Step 8: Run all evolver tests**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/ -v`
Expected: PASS (9 tests)

- [ ] **Step 9: Commit**

```bash
git add agents/bee-evolver/src/hive/models.py \
        agents/bee-evolver/src/hive/transformer/__init__.py \
        agents/bee-evolver/tests/test_usage_capture.py
git commit -m "feat(evolver): capture prompt/completion split and USD per LLM call"
```

---

### Task 3: Evolver cycle timing and guaranteed record

**Files:**
- Modify: `agents/bee-evolver/src/hive/metabolism.py`
- Create: `agents/bee-evolver/tests/test_cycle_record.py`

**Interfaces:**
- Consumes: `MetabolicRecord` (Task 1), `EvolverConnector.write_metabolic_record` (Task 1), `EvolutionPlan.llm_failed` and usage fields (Task 2).
- Produces: a `MetabolicRecord` written on every `EvolverMetabolism.execute()` call, success or failure.

- [ ] **Step 1: Write the failing test**

Create `agents/bee-evolver/tests/test_cycle_record.py`:

```python
import json

import pytest

from config import EvolverSettings
from hive.metabolism import EvolverMetabolism


def _settings(tmp_path) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_SHA="abc1234",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=True,
    )


def _read_record(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


async def test_transformer_failure_still_writes_a_record(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    metabolism = EvolverMetabolism(settings)

    async def _perceive():
        return object()

    async def _boom(_context):
        raise RuntimeError("brain exploded")

    # _configure_git shells out to git; keep the test hermetic.
    monkeypatch.setattr(metabolism, "_configure_git", lambda: None)
    monkeypatch.setattr(metabolism.aggregator, "perceive", _perceive)
    monkeypatch.setattr(metabolism.transformer, "think", _boom)

    with pytest.raises(RuntimeError):
        await metabolism.execute()

    record = _read_record(settings.metabolism_log)
    assert record["outcome"] == "llm_error"
    assert record["bee"] == "evolver"
    assert record["git_sha"] == "abc1234"
    assert record["wall_clock_s"] >= 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_cycle_record.py -v`
Expected: FAIL — `FileNotFoundError` on the log, because no record is written.

- [ ] **Step 3: Implement timing and the finally block**

In `agents/bee-evolver/src/hive/metabolism.py`, add to the imports:

```python
import time

from .records import MetabolicRecord
```

Replace the body of `execute()` so the whole cycle is wrapped. The existing
cycle body is unchanged — it is only indented into the `try`:

```python
    async def execute(self) -> EvolverObservation:
        """Run one complete evolutionary cycle."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        logger.info("evolver_metabolism_started", timestamp=timestamp)

        started = time.monotonic()
        plan = EvolutionPlan()
        outcome = "success"
        proposals = 0
        applied = 0

        try:
            # Configure git identity for CI
            self._configure_git()

            # 1. A — Aggregate: sense the Hive
            context = await self.aggregator.perceive()

            # 2. T — Transform: produce improvement plan
            plan = await self.transformer.think(context)
            if plan.llm_failed:
                outcome = "llm_error"
            proposals = len(plan.improvements)

            branch = ""
            apply_errors: list[str] = []

            if not plan.hive_is_optimal and plan.improvements:
                patchable = [
                    i
                    for i in plan.improvements
                    if i.type in ("code", "prompt", "doc") and i.patch
                ]

                if patchable:
                    # 3. G — Generate: apply patches and push branch
                    try:
                        branch = self.generator.prepare_branch(timestamp)
                        apply_errors = self.generator.apply_improvements(plan)
                        pushed = self.generator.commit_and_push(branch, timestamp)
                        if not pushed:
                            apply_errors.append("Failed to push branch to origin.")
                            branch = ""
                    except Exception as e:
                        logger.error("generator_failed", error=str(e))
                        apply_errors.append(f"Generator error: {e}")
                        branch = ""
                    if apply_errors and outcome == "success":
                        outcome = "generator_error"
                    applied = max(len(patchable) - len(apply_errors), 0)
                else:
                    logger.info(
                        "no_patchable_improvements_skipping_branch",
                        total=len(plan.improvements),
                    )

            # 4. C — Connect: open Issues/PR + Telegram pulse
            observation = await self.connector.act(
                plan=plan,
                branch=branch,
                timestamp=timestamp,
                apply_errors=apply_errors,
            )

            logger.info(
                "evolver_metabolism_completed",
                improvements=len(plan.improvements),
                pr_url=observation.pr_url,
                telegram_sent=observation.telegram_sent,
                errors=len(observation.errors),
            )
            return observation
        except Exception:
            if outcome == "success":
                outcome = "llm_error"
            raise
        finally:
            self.connector.write_metabolic_record(
                MetabolicRecord(
                    ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    bee="evolver",
                    cycle_id=timestamp,
                    git_sha=self.settings.git_sha,
                    model=plan.model_used,
                    llm_calls=plan.llm_calls,
                    prompt_tokens=plan.prompt_tokens,
                    completion_tokens=plan.completion_tokens,
                    usd=plan.usd,
                    wall_clock_s=round(time.monotonic() - started, 3),
                    outcome=outcome,
                    dry_run=self.settings.dry_run,
                    proposals=proposals,
                    applied=applied,
                )
            )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_cycle_record.py -v`
Expected: PASS

- [ ] **Step 5: Run all evolver tests**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/ -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add agents/bee-evolver/src/hive/metabolism.py \
        agents/bee-evolver/tests/test_cycle_record.py
git commit -m "feat(evolver): time every cycle and record it even on failure"
```

---

### Task 4: Evolver dry-run mode

**Files:**
- Modify: `agents/bee-evolver/src/hive/connector/__init__.py`
- Create: `agents/bee-evolver/tests/test_dry_run.py`

**Interfaces:**
- Consumes: `EvolverSettings.dry_run` (Task 1).
- Produces: `EvolverConnector.act()` makes zero outbound HTTP calls when `settings.dry_run` is true.

- [ ] **Step 1: Write the failing test**

Create `agents/bee-evolver/tests/test_dry_run.py`:

```python
import httpx
import pytest

from config import EvolverSettings
from hive.connector import EvolverConnector
from hive.models import EvolutionPlan, Improvement


def _settings(tmp_path, dry_run: bool) -> EvolverSettings:
    return EvolverSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_TOKEN="ghp_realish",
        AURA_TELEGRAM_TOKEN="tg-token",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
        EVOLVER_DRY_RUN=dry_run,
    )


def _plan() -> EvolutionPlan:
    return EvolutionPlan(
        improvements=[
            Improvement(
                type="issue",
                title="Something",
                description="d",
                issue_body="body",
            )
        ],
        narrative="n",
    )


async def test_dry_run_makes_no_http_calls(tmp_path, monkeypatch):
    calls: list[str] = []

    async def _forbid(self, method, url, **kwargs):
        calls.append(url)
        raise AssertionError(f"dry_run must not call {url}")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbid)

    connector = EvolverConnector(_settings(tmp_path, dry_run=True))
    observation = await connector.act(
        plan=_plan(), branch="b", timestamp="20260801-1", apply_errors=[]
    )

    assert calls == []
    assert observation.pr_url == ""
    assert observation.telegram_sent is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_dry_run.py -v`
Expected: FAIL with `AssertionError: dry_run must not call https://api.github.com/...`

- [ ] **Step 3: Implement the short-circuit**

In `agents/bee-evolver/src/hive/connector/__init__.py`, at the very top of `act()`, immediately after the `logger.info("evolver_connector_act_started")` line:

```python
        if self.settings.dry_run:
            logger.info(
                "evolver_connector_dry_run_skipping_outbound",
                improvements=len(plan.improvements),
            )
            return EvolverObservation(
                success=True,
                branch_name=branch,
                errors=list(apply_errors),
                plan=plan,
            )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_dry_run.py -v`
Expected: PASS

- [ ] **Step 5: Run all evolver tests**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/ -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add agents/bee-evolver/src/hive/connector/__init__.py \
        agents/bee-evolver/tests/test_dry_run.py
git commit -m "feat(evolver): add EVOLVER_DRY_RUN to collect a baseline without shipping"
```

---

### Task 5: Keeper record model, writer and settings

**Files:**
- Create: `agents/bee-keeper/src/aura_keeper/hive/records.py`
- Create: `agents/bee-keeper/tests/test_records.py`
- Modify: `agents/bee-keeper/src/aura_keeper/config.py`
- Modify: `agents/bee-keeper/pyproject.toml`
- Modify: `agents/bee-keeper/src/aura_keeper/hive/connector/__init__.py`

**Interfaces:**
- Consumes: nothing (duplicated from Task 1 — `bee.Evolver` must not depend on `aura-core`, so no shared module exists).
- Produces: `MetabolicRecord` (identical shape to Task 1) and `BeeConnector.write_metabolic_record(record) -> None`; `KeeperSettings.metabolism_log`, `.git_sha`.

- [ ] **Step 1: Add the pytest dev group**

In `agents/bee-keeper/pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write the failing test**

Create `agents/bee-keeper/tests/test_records.py`:

```python
import json

from aura_keeper.hive.records import MetabolicRecord


def _record(**overrides) -> MetabolicRecord:
    base = dict(
        ts="2026-08-01T18:40:12Z",
        bee="keeper",
        cycle_id="20260801-184012",
        git_sha="abc1234",
        model="mistral/mistral-large-latest",
        llm_calls=2,
        prompt_tokens=900,
        completion_tokens=120,
        usd=0.004,
        wall_clock_s=12.5,
        outcome="success",
        dry_run=False,
    )
    base.update(overrides)
    return MetabolicRecord(**base)


def test_to_json_line_is_one_line_of_valid_json():
    line = _record().to_json_line()
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line)["llm_calls"] == 2


def test_unknown_usage_serialises_as_null_not_zero():
    parsed = json.loads(
        _record(prompt_tokens=None, completion_tokens=None, usd=None).to_json_line()
    )
    assert parsed["prompt_tokens"] is None
    assert parsed["usd"] is None


def test_scheduled_heartbeat_records_zero_llm_calls():
    # Scheduled runs skip the LLM entirely; that is llm_calls=0 with null usage,
    # and such rows must be excluded from any cost baseline.
    parsed = json.loads(
        _record(
            llm_calls=0, model=None, prompt_tokens=None, completion_tokens=None,
            usd=None,
        ).to_json_line()
    )
    assert parsed["llm_calls"] == 0
    assert parsed["model"] is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd agents/bee-keeper && uv run --group dev pytest tests/test_records.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aura_keeper.hive.records'`

- [ ] **Step 4: Write the record model**

Create `agents/bee-keeper/src/aura_keeper/hive/records.py`. This duplicates the
Evolver's file deliberately — see Interfaces:

```python
"""Per-cycle metabolic record — one JSONL line per metabolic cycle."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal

Outcome = Literal["success", "llm_error", "generator_error", "connector_error"]


@dataclass
class MetabolicRecord:
    """One cycle's cost. Unknown numeric fields are None, never 0."""

    ts: str
    bee: str
    cycle_id: str
    git_sha: str
    model: str | None
    llm_calls: int
    prompt_tokens: int | None
    completion_tokens: int | None
    usd: float | None
    wall_clock_s: float
    outcome: Outcome
    dry_run: bool
    proposals: int | None = None
    applied: int | None = None

    def to_json_line(self) -> str:
        """Serialise to a single newline-terminated JSON line."""
        return json.dumps(asdict(self), sort_keys=True) + "\n"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd agents/bee-keeper && uv run --group dev pytest tests/test_records.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Add settings fields**

In `agents/bee-keeper/src/aura_keeper/config.py`, inside `KeeperSettings`:

```python
    # Metabolism instrumentation (Gate 0)
    metabolism_log: str = Field(
        ".hive/metabolism.jsonl", alias="AURA_METABOLISM_LOG"
    )
    git_sha: str = Field("", alias="GITHUB_SHA")
```

If `Field` is not already imported there, add `from pydantic import Field`.

- [ ] **Step 7: Implement the writer**

In `agents/bee-keeper/src/aura_keeper/hive/connector/__init__.py`, add to the imports:

```python
from pathlib import Path

from ..records import MetabolicRecord
```

and add this method to `BeeConnector`, immediately after `__init__`:

```python
    def write_metabolic_record(self, record: MetabolicRecord) -> None:
        """Append one metabolic record. Never raises — an instrument that
        crashes the organism is worse than no instrument."""
        path = Path(self.settings.metabolism_log)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(record.to_json_line())
        except Exception as e:  # noqa: BLE001 - deliberate: see docstring
            logger.warning(
                "metabolism_write_failed", error=str(e), path=str(path)
            )
```

- [ ] **Step 8: Commit**

```bash
git add agents/bee-keeper/src/aura_keeper/hive/records.py \
        agents/bee-keeper/src/aura_keeper/hive/connector/__init__.py \
        agents/bee-keeper/src/aura_keeper/config.py \
        agents/bee-keeper/pyproject.toml \
        agents/bee-keeper/tests/
git commit -m "feat(keeper): add metabolic record model and append-only writer"
```

---

### Task 6: Keeper usage capture and guaranteed record

**Files:**
- Modify: `agents/bee-keeper/src/aura_keeper/hive/transformer/__init__.py`
- Modify: `agents/bee-keeper/src/aura_keeper/hive/metabolism.py`
- Create: `agents/bee-keeper/tests/test_cycle_record.py`

**Interfaces:**
- Consumes: `MetabolicRecord` and `BeeConnector.write_metabolic_record` (Task 5).
- Produces: `BeeTransformer.usage_totals` — a dict `{"llm_calls": int, "prompt_tokens": int | None, "completion_tokens": int | None, "usd": float | None, "model": str | None}` accumulated across every LLM call in a cycle.

- [ ] **Step 1: Add the accumulator to the Transformer**

In `agents/bee-keeper/src/aura_keeper/hive/transformer/__init__.py`, add these
two module-level helpers after the `logger = ...` line (duplicated from the
Evolver deliberately — the two bees share no package):

```python
def extract_usage(response: Any) -> tuple[int | None, int | None]:
    """Return (prompt_tokens, completion_tokens). None means unknown — never 0,
    because a zero would turn a paid cycle into a free one in the record."""
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None
    return (
        getattr(usage, "prompt_tokens", None),
        getattr(usage, "completion_tokens", None),
    )


def extract_cost(response: Any) -> float | None:
    """USD for this call, or None when the model cannot be priced."""
    try:
        return float(litellm.completion_cost(completion_response=response))
    except Exception as e:  # noqa: BLE001 - unpriceable models are expected
        logger.debug("completion_cost_unavailable", error=str(e))
        return None
```

Then in `BeeTransformer.__init__`, add:

```python
        self.usage_totals: dict[str, object] = {
            "llm_calls": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "usd": None,
            "model": None,
        }
```

and add this method to `BeeTransformer`:

```python
    def _accumulate_usage(self, response: object, model: str) -> None:
        """Sum usage across every LLM call in a cycle.

        bee.Keeper makes more than one call per cycle (_summarize_diff and
        _call_llm); recording only one would undercount its baseline by
        construction. None + value keeps 'unknown' from silently becoming 0.
        """
        prompt, completion = extract_usage(response)
        usd = extract_cost(response)

        def _add(current: object, addition: object) -> object:
            if addition is None:
                return current
            if current is None:
                return addition
            return current + addition

        self.usage_totals["llm_calls"] = int(self.usage_totals["llm_calls"]) + 1
        self.usage_totals["prompt_tokens"] = _add(
            self.usage_totals["prompt_tokens"], prompt
        )
        self.usage_totals["completion_tokens"] = _add(
            self.usage_totals["completion_tokens"], completion
        )
        self.usage_totals["usd"] = _add(self.usage_totals["usd"], usd)
        self.usage_totals["model"] = model
```

- [ ] **Step 2: Call the accumulator at both call sites**

There are exactly two `litellm.acompletion` sites, and they name the model
differently. Handle each explicitly.

In `_summarize_diff` (around line 303), the call passes `model=self.model`.
Immediately after it, before the `return`, add:

```python
            self._accumulate_usage(response, self.model)
```

In `_call_llm` (around line 328), the call passes `**kwargs` where a local
`model` variable exists. Immediately after it, add:

```python
        self._accumulate_usage(response, model)
```

Note `_summarize_diff` wraps its call in `try/except` — the accumulate line goes
**inside** the `try`, after the assignment to `response`, so a failed
summarisation contributes nothing rather than crashing.

- [ ] **Step 3: Write the failing test**

Create `agents/bee-keeper/tests/test_cycle_record.py`:

```python
import json
from types import SimpleNamespace

from aura_keeper.config import KeeperSettings
from aura_keeper.hive.transformer import BeeTransformer


def _settings(tmp_path) -> KeeperSettings:
    return KeeperSettings(
        AURA_LLM__API_KEY="test-key",
        GITHUB_REPOSITORY="zaebee/aura",
        GITHUB_SHA="abc1234",
        AURA_METABOLISM_LOG=str(tmp_path / "metabolism.jsonl"),
    )


def _response(prompt: int, completion: int) -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    )


def test_usage_sums_across_multiple_calls(tmp_path):
    transformer = BeeTransformer(_settings(tmp_path))

    transformer._accumulate_usage(_response(100, 10), "mistral/mistral-large-latest")
    transformer._accumulate_usage(_response(400, 40), "mistral/mistral-large-latest")

    assert transformer.usage_totals["llm_calls"] == 2
    assert transformer.usage_totals["prompt_tokens"] == 500
    assert transformer.usage_totals["completion_tokens"] == 50


def test_unknown_usage_does_not_become_zero(tmp_path):
    transformer = BeeTransformer(_settings(tmp_path))

    transformer._accumulate_usage(SimpleNamespace(), "mistral/mistral-large-latest")

    assert transformer.usage_totals["llm_calls"] == 1
    assert transformer.usage_totals["prompt_tokens"] is None


def test_cycle_writes_a_record(tmp_path):
    from aura_keeper.hive.connector import BeeConnector
    from aura_keeper.hive.records import MetabolicRecord

    settings = _settings(tmp_path)
    connector = BeeConnector(settings)
    connector.write_metabolic_record(
        MetabolicRecord(
            ts="2026-08-01T18:40:12Z",
            bee="keeper",
            cycle_id="c1",
            git_sha=settings.git_sha,
            model=None,
            llm_calls=0,
            prompt_tokens=None,
            completion_tokens=None,
            usd=None,
            wall_clock_s=0.5,
            outcome="success",
            dry_run=False,
        )
    )

    record = json.loads(open(settings.metabolism_log, encoding="utf-8").read())
    assert record["bee"] == "keeper"
    assert record["git_sha"] == "abc1234"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd agents/bee-keeper && uv run --group dev pytest tests/test_cycle_record.py -v`
Expected: FAIL with `AttributeError: 'BeeTransformer' object has no attribute '_accumulate_usage'` if Step 1 was skipped; otherwise it passes and you may proceed.

- [ ] **Step 5: Wire the record into the cycle**

In `agents/bee-keeper/src/aura_keeper/hive/metabolism.py`, add to the imports:

```python
from datetime import UTC, datetime

from .records import MetabolicRecord
```

Replace the whole `execute()` method with this. The cycle body is unchanged —
it is only indented into the `try`. `time` and `start_time` already exist; do
not add a second timer.

```python
    async def execute(self, event_name: str = "scheduled_pulse") -> None:
        """Execute one complete metabolic cycle."""
        logger.info("bee_metabolism_started", trigger_event=event_name)
        start_time = time.time()
        cycle_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        outcome = "success"

        try:
            # 1. Aggregator (A) - Senses the environment
            context = await self.aggregator.perceive(None, event_name=event_name)

            # 2. Transformer (T) - Reasons and audits
            if event_name == "schedule":
                logger.info("scheduled_heartbeat_detected_skipping_llm_audit")
                report = AuditObservation(
                    is_pure=True,
                    narrative=(
                        "The Keeper performs a routine inspection. "
                        "The Hive's pulse is steady."
                    ),
                    reasoning="Scheduled heartbeat run. LLM audit skipped to save honey.",
                )
            else:
                # T now performs deterministic regex audit + reflective LLM analysis
                report = await self.transformer.think(context)

            report.execution_time = float(time.time() - start_time)

            # 3. Connector (C) - Interacts with the outer world (GitHub)
            observation: BeeObservation = await self.connector.act(
                report, context=context
            )

            # Enrich observation with context and report for the Generator
            observation.context = context
            observation.report = report

            # 4. Generator (G) - Updates records and chronicles
            await self.generator.pulse(observation)

            logger.info(
                "bee_metabolism_completed",
                pure=report.is_pure,
                heresies=len(report.heresies),
                execution_time=f"{report.execution_time:.2f}s",
            )
        except Exception:
            outcome = "llm_error"
            raise
        finally:
            totals = self.transformer.usage_totals
            self.connector.write_metabolic_record(
                MetabolicRecord(
                    ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    bee="keeper",
                    cycle_id=cycle_id,
                    git_sha=self.settings.git_sha,
                    model=totals["model"],
                    llm_calls=int(totals["llm_calls"]),
                    prompt_tokens=totals["prompt_tokens"],
                    completion_tokens=totals["completion_tokens"],
                    usd=totals["usd"],
                    wall_clock_s=round(time.time() - start_time, 3),
                    outcome=outcome,
                    dry_run=False,
                )
            )
```

- [ ] **Step 6: Run all keeper tests**

Run: `cd agents/bee-keeper && uv run --group dev pytest tests/ -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Add both suites to `make test`**

In `Makefile`, append to the `test:` target:

```makefile
	# Run bee.Evolver tests
	cd agents/bee-evolver && uv run --group dev pytest tests/ -v
	# Run bee.Keeper tests
	cd agents/bee-keeper && uv run --group dev pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add agents/bee-keeper/src/aura_keeper/hive/transformer/__init__.py \
        agents/bee-keeper/src/aura_keeper/hive/metabolism.py \
        agents/bee-keeper/tests/test_cycle_record.py \
        Makefile
git commit -m "feat(keeper): sum usage across LLM calls and record every cycle"
```

---

### Task 7: Upload the log as a workflow artifact

**Files:**
- Modify: `.github/workflows/bee-evolver.yaml`
- Modify: `.github/workflows/bee-keeper.yaml`

**Interfaces:**
- Consumes: the log path written by Tasks 1–6.
- Produces: artifacts named `metabolism-evolver-<run_id>` and `metabolism-keeper-<run_id>`, each containing `.hive/metabolism.jsonl`.

- [ ] **Step 1: Add the env var and upload step to bee-evolver**

In `.github/workflows/bee-evolver.yaml`, add to the `Run bee.Evolver` step's `env:` block:

```yaml
          AURA_METABOLISM_LOG: ".hive/metabolism.jsonl"
          GITHUB_SHA: ${{ github.sha }}
```

Then add these two steps **after** the `Run bee.Evolver` step:

```yaml
      - name: Assert metabolic record was written
        if: always()
        run: |
          if [ ! -s .hive/metabolism.jsonl ]; then
            echo "::error::No metabolic record written — instrumentation is broken."
            exit 1
          fi
          wc -l .hive/metabolism.jsonl

      - name: Upload metabolic record
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: metabolism-evolver-${{ github.run_id }}
          path: .hive/metabolism.jsonl
          retention-days: 90
```

The `if: always()` on both is deliberate: a failed cycle is exactly the case whose cost must still be captured.

- [ ] **Step 2: Add the same to bee-keeper**

In `.github/workflows/bee-keeper.yaml`, add to the `Run bee.Keeper` step's `env:` block:

```yaml
          AURA_METABOLISM_LOG: ".hive/metabolism.jsonl"
          GITHUB_SHA: ${{ github.sha }}
```

and add the same two steps after it, with the artifact name changed:

```yaml
      - name: Assert metabolic record was written
        if: always()
        run: |
          if [ ! -s .hive/metabolism.jsonl ]; then
            echo "::error::No metabolic record written — instrumentation is broken."
            exit 1
          fi
          wc -l .hive/metabolism.jsonl

      - name: Upload metabolic record
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: metabolism-keeper-${{ github.run_id }}
          path: .hive/metabolism.jsonl
          retention-days: 90
```

- [ ] **Step 3: Verify the YAML parses**

Run: `python3 -c "import yaml,sys; [yaml.safe_load(open(p)) for p in ['.github/workflows/bee-evolver.yaml','.github/workflows/bee-keeper.yaml']]; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/bee-evolver.yaml .github/workflows/bee-keeper.yaml
git commit -m "ci: upload per-cycle metabolic records as artifacts"
```

---

### Task 8: Aggregation workflow

**Files:**
- Create: `tools/aggregate_metabolism.py`
- Create: `agents/bee-evolver/tests/test_aggregate.py`
- Create: `.github/workflows/metabolism-aggregate.yaml`
- Modify: `.github/workflows/bee-keeper.yaml` (extend `paths-ignore`)

**Interfaces:**
- Consumes: artifacts produced by Task 7.
- Produces: `aggregate(lines: list[str]) -> tuple[list[str], int]` returning deduplicated lines and the count of rows with unknown usage; a committed `.hive/metabolism.jsonl` on `main`.

- [ ] **Step 1: Write the failing test**

Create `agents/bee-evolver/tests/test_aggregate.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from aggregate_metabolism import aggregate  # noqa: E402


def _line(cycle_id: str, prompt_tokens=10) -> str:
    return json.dumps(
        {"cycle_id": cycle_id, "bee": "evolver", "prompt_tokens": prompt_tokens}
    )


def test_deduplicates_by_cycle_id():
    lines, _ = aggregate([_line("a"), _line("b"), _line("a")])
    assert len(lines) == 2
    assert [json.loads(x)["cycle_id"] for x in lines] == ["a", "b"]


def test_counts_rows_with_unknown_usage():
    lines, unknown = aggregate([_line("a"), _line("b", prompt_tokens=None)])
    assert len(lines) == 2
    assert unknown == 1


def test_skips_malformed_lines():
    lines, _ = aggregate([_line("a"), "not json", ""])
    assert len(lines) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aggregate_metabolism'`

- [ ] **Step 3: Write the aggregator**

Create `tools/aggregate_metabolism.py`:

```python
"""Merge per-run metabolic records into one deduplicated JSONL file.

Runs outside the measured loop, so it may commit freely.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def aggregate(lines: list[str]) -> tuple[list[str], int]:
    """Deduplicate by cycle_id, preserving first-seen order.

    Returns (deduplicated_lines, unknown_usage_count). The second value must be
    reported: rows with unknown usage cannot enter a cost baseline, and a large
    share of them means the data is unusable rather than merely noisy.
    """
    seen: set[str] = set()
    kept: list[str] = []
    unknown = 0

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        cycle_id = record.get("cycle_id")
        if cycle_id in seen:
            continue
        seen.add(cycle_id)
        kept.append(raw)
        if record.get("prompt_tokens") is None:
            unknown += 1

    return kept, unknown


def main() -> int:
    out = Path(sys.argv[1])
    sources = [Path(p) for p in sys.argv[2:]]

    lines: list[str] = []
    if out.exists():
        lines.extend(out.read_text(encoding="utf-8").splitlines())
    for source in sources:
        lines.extend(source.read_text(encoding="utf-8").splitlines())

    kept, unknown = aggregate(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(kept) + "\n", encoding="utf-8")

    total = len(kept)
    share = (unknown / total * 100) if total else 0.0
    sys.stdout.write(
        f"records={total} unknown_usage={unknown} ({share:.1f}%)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/test_aggregate.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Extend bee-keeper's paths-ignore**

In `.github/workflows/bee-keeper.yaml`, add `.hive/metabolism.jsonl` to **both** `paths-ignore` lists (the `pull_request` one and the `push` one):

```yaml
      - 'HIVE_STATE.md'
      - 'CHRONICLES.md'
      - 'llms.txt'
      - '.hive/metabolism.jsonl'
```

Without this the aggregation commit wakes the Keeper — the same reason `HIVE_STATE.md` is already listed.

- [ ] **Step 6: Create the aggregation workflow**

Create `.github/workflows/metabolism-aggregate.yaml`:

```yaml
name: Metabolism Aggregate

on:
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:

jobs:
  aggregate:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      actions: read

    steps:
      - name: Checkout Hive
        uses: actions/checkout@v4

      - name: Download metabolic artifacts
        uses: actions/download-artifact@v4
        with:
          pattern: metabolism-*
          path: .artifacts
          merge-multiple: false
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Merge records
        run: |
          shopt -s nullglob
          files=(.artifacts/*/metabolism.jsonl)
          if [ ${#files[@]} -eq 0 ]; then
            echo "No artifacts to merge."
            exit 0
          fi
          python3 tools/aggregate_metabolism.py .hive/metabolism.jsonl "${files[@]}"

      - name: Commit if changed
        run: |
          git config user.name "aura-metabolism"
          git config user.email "metabolism@aura.hive"
          if git diff --quiet -- .hive/metabolism.jsonl; then
            echo "No new records."
            exit 0
          fi
          git add .hive/metabolism.jsonl
          git commit -m "chore(metabolism): aggregate per-cycle cost records"
          git push
```

- [ ] **Step 7: Verify the YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/metabolism-aggregate.yaml')); print('ok')"`
Expected: `ok`

- [ ] **Step 8: Run the full suite**

Run: `cd agents/bee-evolver && uv run --group dev pytest tests/ -v && cd ../bee-keeper && uv run --group dev pytest tests/ -v`
Expected: PASS (14 evolver + keeper tests total)

- [ ] **Step 9: Commit**

```bash
git add tools/aggregate_metabolism.py \
        agents/bee-evolver/tests/test_aggregate.py \
        .github/workflows/metabolism-aggregate.yaml \
        .github/workflows/bee-keeper.yaml
git commit -m "ci: aggregate metabolic artifacts into a durable JSONL record"
```

---

## Verification after merge

1. Merge with `EVOLVER_DRY_RUN` unset — behaviour is identical to today.
2. On the next `bee.Keeper` run (any PR or push), confirm the
   `metabolism-keeper-*` artifact exists and every line parses as JSON.
3. Confirm the `Assert metabolic record was written` step is green — a red one
   means the writer is silently failing.
4. Run `Metabolism Aggregate` manually once and read the
   `records=… unknown_usage=… (…%)` line. **A high unknown share means the
   baseline is unusable — that is a stop-and-report result, not something to
   average around.**
5. Only then raise `bee.Evolver` cadence with `EVOLVER_DRY_RUN: "true"`.

## Known gaps, deliberately not closed here

- `bee.Keeper` skips the LLM entirely on `schedule` events
  (`metabolism.py`: `scheduled_heartbeat_detected_skipping_llm_audit`). Those
  cycles record `llm_calls: 0` with null usage and **must be filtered out of any
  cost baseline.** The aggregator does not filter them — filtering is an
  analysis decision, and the raw record should stay raw.
- `bee.Evolver` has no preflight (no pytest/mypy/ruff in its source or
  workflow), so `applied` counts patches that applied cleanly, not proposals
  that passed a check. Any downstream guardrail phrased in terms of "acceptance"
  needs that preflight to exist first.
