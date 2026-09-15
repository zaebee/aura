# Membrane Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `core/src/aura_hive/hive/membrane/main.py` (1174 lines) into focused modules plus stage collaborators, keeping the public contract byte-identical.

**Architecture:** Pure helpers move verbatim into `verdict.py` / `shaping.py` / `metrics.py`; `HiveMembrane` keeps its methods but delegates stage work to `InboundScreening` and an `OutboundPipeline` of `Attestation` / `Postcondition` / `Substitution` collaborators built in `__init__` from the existing registry and settings.

**Tech Stack:** Python 3.12, existing core venv (`uv sync --package core --inexact`), pytest with `@pytest.mark.asyncio`, ruff + mypy pre-commit hooks.

**Spec:** `docs/superpowers/specs/2026-09-15-membrane-decomposition-design.md`

## Global Constraints

- Public surface stays byte-identical: `HiveMembrane`, `inspect_inbound`, `inspect_outbound`, Trinity `bind`/`initialize`/`execute` (there is no bind/initialize on the membrane — do not add any).
- No new error types: violations stay on the `SafetyViolation` path, unavailability on `GuardUnavailable`.
- `receipt.py` is untouched.
- ruff check + format clean and the mypy hook passing on every commit.
- Run core tests with `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`.

---

### Task 1: Pure modules out, re-exports keep importers alive

**Files:**
- Create: `core/src/aura_hive/hive/membrane/verdict.py`
- Create: `core/src/aura_hive/hive/membrane/shaping.py`
- Create: `core/src/aura_hive/hive/membrane/metrics.py`
- Modify: `core/src/aura_hive/hive/membrane/main.py` (replace moved blocks with imports + re-exports)
- Test: existing `core/tests/test_membrane_*.py` (must pass unmodified)

**Interfaces:**
- Consumes: nothing new.
- Produces: `verdict.Verdict` (moved `_Verdict` — keep the underscore name ` _Verdict` exactly, tests import it), `shaping` helpers (`_mint_for`, `_as_dict`, `_replacing`, `_rejection`, `_context_number`, `_quoted_price`, `_neutral_price_message`, `_action_label` — keep underscore names), `metrics` (`_get_counter`, `membrane_interventions_total`, `_record_intervention`), and the `_EMIT`/`_OVERRIDE`/`_REFUSE`/`_UNAVAILABLE` constants which move to `verdict.py` next to their only consumer.

- [ ] **Step 1: Create `verdict.py` with `_Verdict` verbatim**

Copy lines 87–211 of `main.py` exactly as-is: the `_EMIT`/`_OVERRIDE`/`_REFUSE`/`_UNAVAILABLE` casts (lines 87–94), the full `_Verdict` class with its docstring (lines 96–211). Adjust only imports at the top of the new file:

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from aura_core_gen.aura.core.v1 import (
    DecisionDerivation,
    DecisionOutcome,
    Intent,
)

logger = structlog.get_logger(__name__)
```

(`datetime`/`UTC` are used by `_mint_for` — do NOT copy them here; if ruff flags unused imports in `verdict.py`, drop exactly the unused ones. `Intent` is needed only if referenced — check after the move and drop what is unused.)

- [ ] **Step 2: Create `shaping.py` with the Intent helpers verbatim**

Copy lines 213–373 of `main.py` exactly: `_mint_for`, `_as_dict`, `_replacing`, `_rejection`, `_context_number`, `_quoted_price`, `_neutral_price_message`, `_action_label`, with imports:

```python
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import ActionType, Intent

from .receipt import mint
from .verdict import _Verdict

logger = structlog.get_logger(__name__)
```

Verify each name used by the moved bodies is imported (`make_struct` is used by `_replacing`; `mint` by `_mint_for`; `ActionType`, `Intent`, `cast`, `Any`, `datetime`/`UTC`, `structlog`). Run ruff and delete precisely what it flags — nothing more.

- [ ] **Step 3: Create `metrics.py` with the counters verbatim**

Copy lines 33–84 of `main.py` exactly: `_get_counter`, the `membrane_interventions_total` instance, `_record_intervention`, with imports:

```python
from typing import Any, cast

import structlog
from prometheus_client import REGISTRY, Counter

logger = structlog.get_logger(__name__)
```

Keep the comment explaining why this lives here and not in the telemetry protein (it moves with the code).

- [ ] **Step 4: Rewire `main.py` to import + re-export**

Delete the moved blocks from `main.py` and add at the top (after existing imports):

```python
from .metrics import _get_counter, _record_intervention, membrane_interventions_total
from .shaping import (
    _action_label,
    _as_dict,
    _context_number,
    _mint_for,
    _neutral_price_message,
    _quoted_price,
    _rejection,
    _replacing,
)
from .verdict import _EMIT, _OVERRIDE, _REFUSE, _UNAVAILABLE, _Verdict
```

Every name above must be actually used in the remaining `main.py` body (they are: gates, verdict, receipts, messages) so ruff sees no unused imports. Drop now-unused top imports from `main.py` only as ruff directs (`uuid`? `dataclass`? `Counter`? `REGISTRY`? — check each, keep `structlog`/`logger` which the class still uses).

- [ ] **Step 5: Run the membrane tests unmodified**

Run: `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/test_membrane_derivation.py core/tests/test_membrane_outcome.py core/tests/test_membrane_metrics.py core/tests/test_membrane_postcondition.py -q`
Expected: PASS, zero test edits. (These files import privates from `membrane.main` — the re-exports exist for exactly this.)

- [ ] **Step 6: Run the full core suite + ruff**

Run: `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`
Expected: same pass count as main (701 at time of writing).
Run: `.venv/bin/ruff check core/src/aura_hive/hive/membrane/ && .venv/bin/ruff format --check core/src/aura_hive/hive/membrane/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add core/src/aura_hive/hive/membrane/verdict.py core/src/aura_hive/hive/membrane/shaping.py core/src/aura_hive/hive/membrane/metrics.py core/src/aura_hive/hive/membrane/main.py
git commit -m "refactor(membrane): extract verdict, shaping, metrics modules"
```

### Task 2: Stage collaborators, HiveMembrane delegates

**Files:**
- Create: `core/src/aura_hive/hive/membrane/inbound.py`
- Create: `core/src/aura_hive/hive/membrane/outbound.py`
- Modify: `core/src/aura_hive/hive/membrane/main.py` (HiveMembrane only: build collaborators in `__init__`, delegate in `inspect_inbound`/`inspect_outbound`)
- Test: `core/tests/test_membrane_stages.py` (new)

**Interfaces:**
- Consumes: `verdict._Verdict`, `shaping` helpers, `metrics._record_intervention` (Task 1); `registry: SkillRegistry | None`, `settings` (the same objects `HiveMembrane.__init__` already holds).
- Produces: `InboundScreening.check(signal)`, `Attestation.sign(receipt)`, `Postcondition.verify(emission, context)`, `Substitution.offer(reason, context)`, `OutboundPipeline.run(decision, context, verdict)` — all `async`, all raising exactly what the moved bodies raise today.

- [ ] **Step 1: Create `inbound.py`**

Move the body of `HiveMembrane.inspect_inbound` (lines 543–630 of the ORIGINAL `main.py` — re-locate by method name after Task 1, line numbers shifted) verbatim into:

```python
from typing import Any


class InboundScreening:
    """Inbound side of the Membrane. Stateless: the body it carries
    touches no instance state (verified), so it takes no constructor args."""

    async def check(self, signal: Any) -> Any:
        <exact moved body>
```

- [ ] **Step 2: Create `outbound.py` with the four collaborators**

```python
from typing import Any

import structlog
from aura_core_gen.aura.core.v1 import Context, DecisionReceipt, Intent

from .shaping import <whatever the moved bodies reference>
from .verdict import _Verdict

logger = structlog.get_logger(__name__)


class Attestation:
    """Ask the protein that holds the key to sign, or return unsigned."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def sign(self, receipt: DecisionReceipt) -> DecisionReceipt:
        <exact body of HiveMembrane._attest>


class Postcondition:
    """Whether what is about to be sent satisfies the rule set."""

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    async def verify(self, emission: Intent, context: Context) -> bool:
        <exact body of HiveMembrane._postcondition_holds>


class Substitution:
    """The deterministic safe offer and its finishing touches."""

    def __init__(self, registry: Any, settings: Any) -> None:
        self.registry = registry
        self.settings = settings

    async def offer(self, reason: str, context: Context) -> Intent:
        <exact body of HiveMembrane._override_with_safe_offer>

    async def finish(
        self, claim: Intent, emission: Intent, verdict: _Verdict, request_id: str
    ) -> Intent:
        <exact body of HiveMembrane._finish>


class OutboundPipeline:
    """Attest, then postcondition, then substitute-on-violation."""

    def __init__(self, registry: Any, settings: Any) -> None:
        self.attestation = Attestation(registry)
        self.postcondition = Postcondition(registry)
        self.substitution = Substitution(registry, settings)

    async def run(
        self, decision: Intent, context: Context, verdict: _Verdict
    ) -> Intent:
        <exact body of HiveMembrane.inspect_outbound, with
        self._attest(...) -> self.attestation.sign(...),
        self._postcondition_holds(...) -> self.postcondition.verify(...),
        self._override_with_safe_offer(...) -> self.substitution.offer(...),
        self._finish(...) -> self.substitution.finish(...)>
```

Type the constructor params as `Any` only where the current code is already untyped (registry is `SkillRegistry | None` on the membrane — use that exact type, not `Any`). Keep every log line, every exception type, every return shape identical — this task moves code, it designs nothing.

- [ ] **Step 3: Shrink `HiveMembrane` to orchestration**

```python
def __init__(self, registry: SkillRegistry | None = None) -> None:
    self.settings = get_settings()
    self.registry = registry
    self.inbound = InboundScreening()
    self.outbound = OutboundPipeline(registry, self.settings)

async def inspect_inbound(self, signal: Any) -> Any:
    return await self.inbound.check(signal)

async def inspect_outbound(self, decision: Intent, context: Context) -> Intent:
    verdict = _Verdict()
    return await self.outbound.run(decision, context, verdict)
```

(Verify against the actual current `inspect_outbound` head: if it constructs the verdict or reads settings first, keep those exact lines in the delegating method and pass the pieces down — do not silent-drop behavior. Same for `inspect_inbound`.)

- [ ] **Step 4: Write stage tests (new file `core/tests/test_membrane_stages.py`)**

```python
"""Outbound stages in isolation: what the 400-line method hid."""

import pytest
from aura_hive.hive.membrane.outbound import Attestation, Postcondition, Substitution


@pytest.mark.asyncio
async def test_unsigned_receipt_passes_through_when_no_key():
    """Attestation without a wired key returns the receipt unsigned —
    the decision stands, only the proof is absent."""
    from aura_core_gen.aura.core.v1 import DecisionReceipt

    attestation = Attestation(registry=None)
    receipt = DecisionReceipt()
    assert await attestation.sign(receipt) == receipt
```

(Verify `DecisionReceipt()` default-constructs and `==` compares by value in this repo's betterproto setup before committing to that assertion — if not, assert on identity of the returned object or on the version field staying UNSIGNED. Adjust the test to what is true; do not adjust the implementation to fit the test.)

```python
@pytest.mark.asyncio
async def test_postcondition_without_guard_is_unreachable_not_a_pass():
    """No registry means no verdict could be established — False, not True."""
    from unittest.mock import MagicMock

    postcondition = Postcondition(registry=None)
    assert await postcondition.verify(MagicMock(), MagicMock()) is False
```

(Verify the current `_postcondition_holds` returns False (not raises) when `self.registry is None` — the code comment says so; if it raises instead, assert the raise. Test documents reality.)

- [ ] **Step 5: Run new tests to verify they fail-then-pass correctly**

Run: `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/test_membrane_stages.py -v`
Expected: PASS (implementation moved in the same task, so confirm green and confirm each test actually exercises the stage by temporarily... skip mutation games — instead re-run the FULL membrane set below).

- [ ] **Step 6: Run the full membrane + core suites unmodified**

Run: `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/test_membrane_derivation.py core/tests/test_membrane_outcome.py core/tests/test_membrane_metrics.py core/tests/test_membrane_postcondition.py -q`
Expected: PASS with zero edits to those files.
Run: `PYTHONPATH=core/src .venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`
Expected: full pass (701 at time of writing).
Run ruff check + format on `core/src/aura_hive/hive/membrane/`; fix only what ruff flags.

- [ ] **Step 7: Commit**

```bash
git add core/src/aura_hive/hive/membrane/inbound.py core/src/aura_hive/hive/membrane/outbound.py core/src/aura_hive/hive/membrane/main.py core/tests/test_membrane_stages.py
git commit -m "refactor(membrane): stage collaborators, HiveMembrane delegates"
```

### Task 3: Drop transitional re-exports, verify the 250-line bar

**Files:**
- Modify: `core/src/aura_hive/hive/membrane/main.py` (remove re-exports)
- Modify: `core/tests/test_membrane_outcome.py` (import `_Verdict`, `_OVERRIDE`, `_REFUSE`, `_UNAVAILABLE` from `verdict`, not `main`)
- Modify: `core/tests/test_membrane_metrics.py` (import `_get_counter` from `metrics`, not `main`)
- Modify: any other test importing privates from `membrane.main` (find with `grep -rn "from aura_hive.hive.membrane.main import" core/tests/` — only `HiveMembrane` may stay)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `main.py` under 250 lines; `membrane/__init__.py` unchanged (`HiveMembrane` only).

- [ ] **Step 1: Remove re-exports that tests no longer need**

In `main.py`, delete the re-export import block from Task 1 down to exactly the names the remaining body uses. Keep `HiveMembrane` importable from both `membrane.main` and `membrane` (the `__init__.py` line stays).

- [ ] **Step 2: Point the three test files at the new homes**

`test_membrane_outcome.py`: `from aura_hive.hive.membrane.main import (..., _Verdict)` → import `_Verdict`, `_OVERRIDE`, `_REFUSE`, `_UNAVAILABLE` from `aura_hive.hive.membrane.verdict`. `HiveMembrane` stays imported from `main`.
`test_membrane_metrics.py`: `_get_counter` from `aura_hive.hive.membrane.metrics`.
Any other file from the grep: same treatment, `HiveMembrane` always stays on `main`.

- [ ] **Step 3: Verify the bar and the suite**

Run: `wc -l core/src/aura_hive/hive/membrane/main.py`
Expected: under 250.
Run: full core suite + ruff as in Task 2 Step 6.
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add core/src/aura_hive/hive/membrane/main.py core/tests/test_membrane_outcome.py core/tests/test_membrane_metrics.py
git commit -m "refactor(membrane): drop transitional re-exports"
```

(Note: this task edits 2–3 test files' import lines only. That is the documented exception to "tests pass unmodified" — the done-criterion for contract intactness was Tasks 1–2; this task moves the imports the re-exports existed to protect.)
