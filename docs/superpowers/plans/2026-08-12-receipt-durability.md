# Receipt Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make decision receipts outlive the short-retention log they currently live in, and give the auditor one command that turns a `dispute_token` into a verified receipt.

**Architecture:** The Connector writes every receipt to Postgres on the C step, fail-open, through two new capabilities on the persistence protein. The lookup lives in the protein rather than in the tool, so a future internal endpoint is a second thin caller. The `membrane_receipt` log line stays as an independent second path.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (`DeclarativeBase` / `Mapped`), betterproto, pytest, structlog, uv.

**Spec:** `docs/superpowers/specs/2026-08-12-receipt-durability-design.md`

## Global Constraints

- Package manager is `uv`. Never `pip` or `poetry`.
- Run core tests as: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest <path> -v`
- Proteins follow the Trinity pattern: `bind(settings, provider)` → `async initialize() -> bool` → `async execute(intent, params) -> Observation`.
- Entity SQL lives in a repository class, never inline in the skill. Handlers stay thin: `params -> repo -> Observation`. Repository methods are **synchronous**; handlers wrap them in `asyncio.to_thread`.
- Never edit generated protobuf code (`*/gen-proto/`, `aura_core_gen`).
- Biological naming. `Manager`/`Service`/`Helper`/`Handler` are forbidden as type names.
- `make lint` must exit 0 before every commit.
- ruff treats `aura_hive` as third-party: imports sort into one block with `pytest`, `sqlalchemy`, `eth_account` etc., alphabetically. `aura_core` < `aura_core_gen` < `aura_hive` < `pytest` < `sqlalchemy`.
- **Recording a receipt must never fail a decision.** Every write path is fail-open.
- A receipt carries no price and no premise value — only digests, identifiers, enums, timestamps and signature metadata. Nothing in this plan may add one.
- **Verified fact this plan relies on:** `DecisionReceipt().from_dict(json.loads(json.dumps(receipt.to_dict())))` verifies and stays attested. Storing the whole document as JSON is lossless.

---

### Task 1: The row and the repository

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/persistence/engine.py` (add a model after `MetabolicCost`)
- Create: `core/src/aura_hive/hive/proteins/persistence/receipts.py`
- Test: `core/tests/test_receipt_repository.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `DecisionReceiptRecord` — SQLAlchemy model, `__tablename__ = "decision_receipts"`.
  - `ReceiptRepository(session_factory)` with synchronous `record(receipt: dict, dispute_token: str) -> None` and `find_by_dispute_token(token: str) -> dict | None`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_receipt_repository.py`:

```python
"""
Receipts survive the log they used to live in.

`DECISION_RECEIPT.md` §7 says the log line makes the log the store. It does,
for days to weeks: the stream goes to a Loki outside this repository with a
short retention, and nothing wrote a receipt anywhere else. A dispute arriving
a month after the decision found nothing.
"""

import json
from unittest.mock import MagicMock

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.hive.proteins.persistence.receipts import ReceiptRepository


def a_receipt() -> dict:
    """A receipt dict in the shape `to_dict()` produces — camelCase keys."""
    return {
        "version": "AURA-RECEIPT-V2-UNSIGNED",
        "claimHash": "a" * 64,
        "emissionHash": "b" * 64,
        "outcome": "DECISION_OUTCOME_EMIT",
        "outcomeGate": "",
        "canonicalPrefix": "c" * 16,
        "issuedAt": "2026-08-12T10:00:00Z",
        "decisionId": "dec-1111",
        "requestId": "req-2222",
        "rulesetVersion": "guard/negotiation@2.0.0+deadbeef",
    }


def a_session() -> MagicMock:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestRecording:
    def test_the_indexed_columns_are_taken_from_the_document(self) -> None:
        """
        Derived here rather than passed in, so an index cannot disagree with
        the receipt it indexes.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")

        row = session.add.call_args[0][0]
        assert row.dispute_token == "tok-abc"
        assert row.decision_id == "dec-1111"
        assert row.request_id == "req-2222"
        assert row.issued_at == "2026-08-12T10:00:00Z"
        assert row.receipt == a_receipt()
        session.commit.assert_called_once()

    def test_the_whole_document_is_stored_not_a_decomposition(self) -> None:
        """
        `verify()` takes a document. Every normalisation is a chance to
        reassemble something at read time that differs from what was signed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")

        stored = session.add.call_args[0][0].receipt
        assert stored == a_receipt()

    def test_a_stored_receipt_survives_json_and_still_parses(self) -> None:
        """
        The column is JSON, so the document goes through a serialisation the
        receipt never asked for. This is the property the whole archive rests
        on: what comes back must be the document that was signed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        repo.record(a_receipt(), dispute_token="tok-abc")
        stored = session.add.call_args[0][0].receipt

        parsed = DecisionReceipt().from_dict(json.loads(json.dumps(stored)))

        assert parsed.decision_id == "dec-1111"
        assert parsed.claim_hash == "a" * 64
        assert parsed.canonical_prefix == "c" * 16


class TestFinding:
    def test_a_known_token_returns_the_document(self) -> None:
        session = a_session()
        row = MagicMock()
        row.receipt = a_receipt()
        session.query.return_value.filter_by.return_value.first.return_value = row
        repo = ReceiptRepository(MagicMock(return_value=session))

        assert repo.find_by_dispute_token("tok-abc") == a_receipt()

    def test_an_unknown_token_returns_nothing_rather_than_raising(self) -> None:
        """
        A token that was never issued is a legitimate answer to give an
        auditor — someone may have invented it — not a failure.
        """
        session = a_session()
        session.query.return_value.filter_by.return_value.first.return_value = None
        repo = ReceiptRepository(MagicMock(return_value=session))

        assert repo.find_by_dispute_token("never-issued") is None


class TestASessionCanBeReassembled:
    def test_two_decisions_in_one_session_share_a_request_id(self) -> None:
        """
        `request_id` exists so an auditor holding one token can pull the whole
        negotiation rather than the single turn they were cited. Nothing else
        asserts the field, so it would rot unnoticed.
        """
        session = a_session()
        repo = ReceiptRepository(MagicMock(return_value=session))

        first = a_receipt()
        second = a_receipt() | {"decisionId": "dec-3333"}
        repo.record(first, dispute_token="tok-one")
        repo.record(second, dispute_token="tok-two")

        rows = [call[0][0] for call in session.add.call_args_list]
        assert [row.decision_id for row in rows] == ["dec-1111", "dec-3333"]
        assert {row.request_id for row in rows} == {"req-2222"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'aura_hive.hive.proteins.persistence.receipts'`

- [ ] **Step 3: Write minimal implementation**

In `core/src/aura_hive/hive/proteins/persistence/engine.py`, add after the `MetabolicCost` model:

```python
class DecisionReceiptRecord(Base):
    """
    The auditor's copy of a decision receipt.

    The log line was the only store, and it lives in a Loki with a short
    retention — so a dispute arriving a month after the decision found nothing.
    This table is what makes the corpus outlive the stream; the log line stays
    as a second, independent path.

    Nothing here is a price or a premise. Every receipt field is a digest, an
    identifier, an enum, a timestamp or signature metadata, which is why the
    whole document can be stored without becoming a new place the floor lives.
    """

    __tablename__ = "decision_receipts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # What the counterparty cites. The lookup key.
    dispute_token: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    # What the signature binds — the auditor's other way in.
    decision_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # The session, for reassembling a whole negotiation.
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # The receipt's own timestamp, kept as the string it carries rather than
    # parsed into a DateTime, so the column holds what was signed instead of a
    # reconstruction of it.
    issued_at: Mapped[str] = mapped_column(String, nullable=False)
    # The whole document, exactly as the log line carries it.
    receipt: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # When the row was written — deliberately separate from `issued_at`, so a
    # divergence between deciding and recording is visible rather than hidden.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
```

**No import changes are needed.** `engine.py` already imports every name this model uses — `uuid`,
`UTC`, `datetime`, `Any`, `String`, `DateTime`, `JSONB`, `Mapped`, `mapped_column`. Verified against
the file; if ruff disagrees, something else moved and is worth reading before adding anything.

Create `core/src/aura_hive/hive/proteins/persistence/receipts.py`:

```python
"""ReceiptRepository — the auditor's copy of every decision receipt.

Keeps the receipt SQL in one place so the skill's handlers stay thin
(params -> repo -> Observation). Methods are synchronous; callers wrap them in
``asyncio.to_thread`` exactly as the other repositories are called.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from .engine import DecisionReceiptRecord


class ReceiptRepository:
    """Write-once storage for decision receipts, read by dispute token."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session = session_factory

    def record(self, receipt: dict[str, Any], dispute_token: str) -> None:
        """
        Store a receipt under the token the counterparty was given.

        The indexed columns are derived from the document rather than passed
        in beside it, so an index cannot come to disagree with the receipt it
        indexes.
        """
        with self._session() as session:
            session.add(
                DecisionReceiptRecord(
                    dispute_token=dispute_token,
                    decision_id=str(receipt.get("decisionId", "")),
                    request_id=str(receipt.get("requestId", "")),
                    issued_at=str(receipt.get("issuedAt", "")),
                    receipt=receipt,
                )
            )
            session.commit()

    def find_by_dispute_token(self, token: str) -> dict[str, Any] | None:
        """The document, or None. An unissued token is an answer, not a fault."""
        with self._session() as session:
            row = (
                session.query(DecisionReceiptRecord)
                .filter_by(dispute_token=token)
                .first()
            )
            return dict(row.receipt) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_repository.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/proteins/persistence/engine.py core/src/aura_hive/hive/proteins/persistence/receipts.py core/tests/test_receipt_repository.py
git commit -m "feat(persistence): a table that outlives the log receipts were stored in"
```

---

### Task 2: The two capabilities

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/persistence/skill.py` (`_capabilities` map ~line 48-65; repository wiring ~line 69-71; new handlers beside `_get_deal_by_memo_handler`)
- Test: `core/tests/test_receipt_capabilities.py`

**Interfaces:**
- Consumes: `ReceiptRepository` from Task 1.
- Produces:
  - `record_receipt` — params `{"receipt": dict, "dispute_token": str}` → `Observation(success=True)`, or `Observation(success=False, error=...)`.
  - `find_receipt_by_dispute_token` — params `{"dispute_token": str}` → `Observation(success=True, metadata={"receipt": dict})` or `Observation(success=False, error="not_found")`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_receipt_capabilities.py`:

```python
"""
The lookup lives in the protein, not in the tool.

A `make resolve-dispute` command and a future internal endpoint should be two
thin callers of one query rather than two implementations of it.
"""

from unittest.mock import MagicMock

import pytest
from aura_hive.config.database import DatabaseSettings
from aura_hive.hive.proteins.persistence.skill import PersistenceSkill


def a_receipt() -> dict:
    return {
        "version": "AURA-RECEIPT-V2-UNSIGNED",
        "claimHash": "a" * 64,
        "decisionId": "dec-1111",
        "requestId": "req-2222",
        "issuedAt": "2026-08-12T10:00:00Z",
    }


def skill_with(session: MagicMock) -> PersistenceSkill:
    skill = PersistenceSkill()
    settings = DatabaseSettings(
        url="postgresql://user:password@localhost:5432/aura_db",
        redis_url="redis://localhost:6379/0",
    )
    skill.bind(settings, (MagicMock(return_value=session), MagicMock(), None))
    return skill


def a_session() -> MagicMock:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


class TestRecording:
    @pytest.mark.asyncio
    async def test_a_receipt_is_recorded_under_its_token(self) -> None:
        session = a_session()

        obs = await skill_with(session).execute(
            "record_receipt", {"receipt": a_receipt(), "dispute_token": "tok-abc"}
        )

        assert obs.success
        assert session.add.call_args[0][0].dispute_token == "tok-abc"

    @pytest.mark.asyncio
    async def test_a_missing_token_is_refused_by_value(self) -> None:
        obs = await skill_with(a_session()).execute(
            "record_receipt", {"receipt": a_receipt()}
        )

        assert not obs.success
        assert obs.error == "dispute_token_required"

    @pytest.mark.asyncio
    async def test_a_missing_receipt_is_refused_by_value(self) -> None:
        obs = await skill_with(a_session()).execute(
            "record_receipt", {"dispute_token": "tok-abc"}
        )

        assert not obs.success
        assert obs.error == "receipt_required"

    @pytest.mark.asyncio
    async def test_a_database_failure_is_reported_not_raised(self) -> None:
        """
        The Connector treats this as fail-open, so it must come back as a
        failed Observation rather than an exception crossing the boundary.
        """
        session = a_session()
        session.commit.side_effect = RuntimeError("connection refused")

        obs = await skill_with(session).execute(
            "record_receipt", {"receipt": a_receipt(), "dispute_token": "tok-abc"}
        )

        assert not obs.success
        assert "connection refused" in (obs.error or "")


class TestFinding:
    @pytest.mark.asyncio
    async def test_a_known_token_returns_the_document(self) -> None:
        session = a_session()
        row = MagicMock()
        row.receipt = a_receipt()
        session.query.return_value.filter_by.return_value.first.return_value = row

        obs = await skill_with(session).execute(
            "find_receipt_by_dispute_token", {"dispute_token": "tok-abc"}
        )

        assert obs.success
        assert obs.metadata.to_dict()["receipt"]["decisionId"] == "dec-1111"

    @pytest.mark.asyncio
    async def test_an_unknown_token_is_not_found_rather_than_an_error(self) -> None:
        session = a_session()
        session.query.return_value.filter_by.return_value.first.return_value = None

        obs = await skill_with(session).execute(
            "find_receipt_by_dispute_token", {"dispute_token": "never-issued"}
        )

        assert not obs.success
        assert obs.error == "not_found"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_capabilities.py -v`
Expected: FAIL — `Unknown intent: record_receipt`

- [ ] **Step 3: Write minimal implementation**

In `skill.py`, import the repository beside the others:

```python
from .receipts import ReceiptRepository
```

Add to the `_capabilities` map, after `"log_metabolic_cost"`:

```python
            "record_receipt": self._record_receipt,
            "find_receipt_by_dispute_token": self._find_receipt_by_dispute_token,
```

Wire the repository beside `self._wallets`:

```python
        self._receipts = ReceiptRepository(self._get_session)
```

Add the two handlers beside `_get_deal_by_memo_handler`:

```python
    async def _record_receipt(self, params: dict[str, Any]) -> Observation:
        """
        Store the auditor's copy. Failure is reported, never raised: the
        Connector treats this as fail-open, because reporting on a decision
        must not take that decision down.
        """
        receipt = params.get("receipt")
        if not receipt:
            return Observation(success=False, error="receipt_required")
        dispute_token = params.get("dispute_token")
        if not dispute_token:
            return Observation(success=False, error="dispute_token_required")

        try:
            await asyncio.to_thread(self._receipts.record, receipt, dispute_token)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _find_receipt_by_dispute_token(
        self, params: dict[str, Any]
    ) -> Observation:
        """
        The query lives here rather than in the tool that calls it, so a
        future internal endpoint is a second thin caller rather than a second
        implementation.
        """
        token = params.get("dispute_token")
        if not token:
            return Observation(success=False, error="dispute_token_required")

        result = await asyncio.to_thread(
            self._receipts.find_by_dispute_token, token
        )
        if result is None:
            # Not an error. A token that was never issued is a legitimate
            # answer to give an auditor — someone may have invented it.
            return Observation(success=False, error="not_found")
        return Observation(success=True, metadata=make_struct({"receipt": result}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_capabilities.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the persistence suite**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_persistence_skill.py core/tests/test_persistence_wallet.py -v`
Expected: PASS — the capability map grew, nothing else changed.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/proteins/persistence/skill.py core/tests/test_receipt_capabilities.py
git commit -m "feat(persistence): record and resolve a receipt by its dispute token"
```

---

### Task 3: The Connector records every decision

**Files:**
- Modify: `core/src/aura_hive/hive/connector/main.py` (add an `act` override on `HiveConnector`, after `__init__` at line ~42-46)
- Test: `core/tests/test_receipt_recording.py`

**Interfaces:**
- Consumes: `record_receipt` from Task 2.
- Produces: `HiveConnector.act(action, context)` — records the receipt, then delegates to `BaseConnector.act`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_receipt_recording.py`:

```python
"""
Every decision is archived, including the ones that refused.

`MetabolicLoop` calls `connector.act` unconditionally after the outbound
Membrane, so a refusal reaches the Connector like anything else — and "you
refused me" is the likeliest dispute a counterparty brings.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    DecisionReceipt,
    HiveContextData,
    Intent,
    NegotiationIntent,
    Observation,
)
from aura_hive.hive.connector.main import HiveConnector


def a_decision(action: ActionType, token: str = "tok-abc") -> Intent:
    intent = Intent(
        action=action,
        reasoning="LLM reasoning",
        negotiation=NegotiationIntent(price=1200.0, message="offer"),
    )
    intent.dispute_token = token
    intent.receipt = DecisionReceipt(
        version="AURA-RECEIPT-V2-UNSIGNED",
        decision_id="dec-1111",
        request_id="req-2222",
        issued_at="2026-08-12T10:00:00Z",
    )
    return intent


def a_context() -> Context:
    return Context(hive=HiveContextData(request_id="req-2222"))


def connector_with(registry: MagicMock) -> HiveConnector:
    return HiveConnector(registry=registry)


def a_registry(record_result: Any = None) -> MagicMock:
    registry = MagicMock()
    registry.execute = AsyncMock(
        return_value=record_result or Observation(success=True)
    )
    return registry


class TestTheArchiveIsWritten:
    @pytest.mark.asyncio
    async def test_an_emitted_decision_is_recorded_under_its_token(self) -> None:
        registry = a_registry()

        await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        call = next(
            c for c in registry.execute.await_args_list if c[0][1] == "record_receipt"
        )
        assert call[0][0] == "persistence"
        assert call[0][2]["dispute_token"] == "tok-abc"
        assert call[0][2]["receipt"]["decisionId"] == "dec-1111"

    @pytest.mark.asyncio
    async def test_a_refused_decision_is_recorded_too(self) -> None:
        """The dispute most likely to arrive is about a refusal."""
        registry = a_registry()

        await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_REJECT), a_context()
        )

        assert any(
            c[0][1] == "record_receipt" for c in registry.execute.await_args_list
        )

    @pytest.mark.asyncio
    async def test_a_decision_with_no_receipt_records_nothing(self) -> None:
        """An unwired Membrane mints none; there is nothing to archive."""
        registry = a_registry()
        intent = Intent(action=ActionType.ACTION_TYPE_COUNTER, reasoning="x")

        await connector_with(registry).act(intent, a_context())

        assert not any(
            c[0][1] == "record_receipt" for c in registry.execute.await_args_list
        )


class TestTheArchiveNeverCostsTheDecision:
    @pytest.mark.asyncio
    async def test_a_failed_write_still_returns_an_observation(self) -> None:
        registry = a_registry(Observation(success=False, error="connection refused"))

        observation = await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        assert observation is not None

    @pytest.mark.asyncio
    async def test_a_raising_write_still_returns_an_observation(self) -> None:
        """
        The promise has to hold from where the code sits, not from someone
        having checked that the protein never raises.
        """
        registry = MagicMock()
        registry.execute = AsyncMock(side_effect=RuntimeError("pool exhausted"))

        observation = await connector_with(registry).act(
            a_decision(ActionType.ACTION_TYPE_COUNTER), a_context()
        )

        assert observation is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_recording.py -v`
Expected: FAIL — no `record_receipt` call is ever made, so `next(...)` raises `StopIteration` and the fail-open tests error on the registry mock.

- [ ] **Step 3: Write minimal implementation**

In `core/src/aura_hive/hive/connector/main.py`, add to `HiveConnector` immediately after `__init__`:

Note the parameter types: `BaseConnector.act` is declared `(action: Any, context: Any)`, so the
override must not narrow them to `Intent`/`Context` — mypy rejects that as a Liskov violation and
`make lint` will refuse the commit. `_record_receipt` takes the narrow type, since nothing overrides
it.

```python
    async def act(self, action: Any, context: Any) -> Observation:
        """
        Archive the receipt, then act.

        Written here rather than in the Membrane that mints it: this is the
        step that performs I/O, and putting a Postgres round-trip inside a
        boundary check would pay negotiation latency for an archive. The
        Genome's `act` dispatches steps or falls back to `_handle_legacy`, and
        recording before that delegation means every decision is archived on
        both paths — including the refusals, which are the disputes most
        likely to arrive.
        """
        await self._record_receipt(action)
        return await super().act(action, context)

    async def _record_receipt(self, action: Intent) -> None:
        """
        Fail-open, deliberately and completely.

        The rule the receipt log line already follows: reporting on a decision
        must never take that decision down. The cost is that archive holes are
        possible and silent, which is why the failure is its own event — an
        archive that sometimes never arrives is worse than one that expires,
        because nothing announces it.
        """
        if not action.receipt or not action.dispute_token:
            return

        try:
            observation = await self.registry.execute(
                "persistence",
                "record_receipt",
                {
                    "receipt": action.receipt.to_dict(),
                    "dispute_token": action.dispute_token,
                },
            )
            if not observation.success:
                logger.warning(
                    "receipt_record_failed",
                    dispute_token=action.dispute_token,
                    error=observation.error,
                )
        except Exception as e:
            logger.warning(
                "receipt_record_failed",
                dispute_token=action.dispute_token,
                error=str(e),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_receipt_recording.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the whole core suite**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -q`
Expected: all pass. `HiveConnector.act` is now on the path of every connector test; if one breaks, its registry mock is returning something the recording path cannot read — fix the mock, not the fail-open guarantee.

- [ ] **Step 6: Lint and commit**

```bash
make lint
git add core/src/aura_hive/hive/connector/main.py core/tests/test_receipt_recording.py
git commit -m "feat(connector): archive every receipt, including the refusals"
```

---

### Task 4: The auditor's command

**Files:**
- Create: `tools/resolve_dispute.py`
- Modify: `Makefile` (add a target beside `verify-receipts` at line ~203)
- Test: `core/tests/test_resolve_dispute_tool.py`

**Interfaces:**
- Consumes: `find_receipt_by_dispute_token` from Task 2.
- Produces: `resolve(receipt_dict) -> tuple[str, int]` — the printable report and the exit code.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_resolve_dispute_tool.py`:

```python
"""
What an auditor gets when a counterparty cites a token.

Not just the document: the document plus whether it holds up. In a dispute the
second question is the one being asked.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from resolve_dispute import render  # noqa: E402


def an_unsigned_receipt() -> dict:
    return {
        "version": "AURA-RECEIPT-V2-UNSIGNED",
        "claimHash": "a" * 64,
        "emissionHash": "a" * 64,
        "outcome": "DECISION_OUTCOME_EMIT",
        "canonicalPrefix": "c" * 16,
        "issuedAt": "2026-08-12T10:00:00Z",
        "decisionId": "dec-1111",
        "requestId": "req-2222",
        "rulesetVersion": "guard/negotiation@2.0.0+deadbeef",
    }


def test_a_found_receipt_is_reported_with_its_verdict() -> None:
    report, code = render(an_unsigned_receipt())

    assert "dec-1111" in report
    assert "req-2222" in report
    assert "verify" in report.lower()
    assert code == 0


def test_an_unsigned_receipt_is_named_as_unattested() -> None:
    """
    The auditor must not read "verified" as "vouched for". §7 keeps the two
    version names apart precisely so this distinction survives.
    """
    report, _ = render(an_unsigned_receipt())

    assert "not attested" in report.lower()


def test_a_missing_receipt_is_an_answer_not_a_failure() -> None:
    """
    A token that was never issued is a legitimate thing to tell an auditor.
    Exit 0, because the tool answered.
    """
    report, code = render(None)

    assert "not found" in report.lower()
    assert code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_resolve_dispute_tool.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'resolve_dispute'`

- [ ] **Step 3: Write minimal implementation**

Create `tools/resolve_dispute.py`:

```python
"""
Resolve a dispute token into the receipt it names, and say whether it holds.

`make resolve-dispute TOKEN=…`

The counterparty holds a random per-decision token and nothing else — no
digest, no prefix, nothing derived from the decision (§3.4). This is the tool
that turns that citation into the decision an auditor can read.

The query itself lives in the persistence protein rather than here, so an
internal endpoint later is a second thin caller rather than a second
implementation.
"""

import argparse
import asyncio
import json
import sys
from typing import Any

from aura_core_gen.aura.core.v1 import DecisionReceipt
from aura_hive.config import get_settings
from aura_hive.hive.cortex import HiveCell
from aura_hive.hive.membrane.receipt import verify


def render(receipt: dict[str, Any] | None) -> tuple[str, int]:
    """
    The report and the exit code.

    A token nobody issued is an answer rather than a fault, so it exits 0. The
    tool failing to reach the database is a different thing and exits non-zero
    — that is the tool not answering, handled by the caller below.
    """
    if receipt is None:
        return ("not found — no decision was recorded under that token", 0)

    parsed = DecisionReceipt().from_dict(receipt)
    result = verify(parsed)

    lines = [
        f"decision_id    {parsed.decision_id}",
        f"request_id     {parsed.request_id}",
        f"issued_at      {parsed.issued_at}",
        f"outcome        {parsed.outcome}",
        f"outcome_gate   {parsed.outcome_gate or '—'}",
        f"override_scope {parsed.override_scope or '—'}",
        f"claim_hash     {parsed.claim_hash}",
        f"emission_hash  {parsed.emission_hash}",
        "",
        f"verify         {'ok' if result.ok else 'FAILED'}",
        f"               {'attested' if result.attested else 'not attested'}",
    ]
    for failure in result.failures:
        lines.append(f"  failure      {failure}")
    if result.unverifiable:
        lines.append(f"  unverifiable {', '.join(result.unverifiable)}")
    lines.append("")
    lines.append(json.dumps(receipt, indent=2, sort_keys=True))

    return ("\n".join(lines), 0 if result.ok else 1)


async def _lookup(token: str) -> dict[str, Any] | None:
    cell = HiveCell(get_settings())
    await cell._init_proteins()
    observation = await cell.registry.execute(
        "persistence", "find_receipt_by_dispute_token", {"dispute_token": token}
    )
    if not observation.success:
        if observation.error == "not_found":
            return None
        raise RuntimeError(observation.error)
    meta = observation.metadata.to_dict() if observation.metadata else {}
    return dict(meta.get("receipt") or {})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token", help="the dispute_token the counterparty cited")
    args = parser.parse_args()

    try:
        receipt = asyncio.run(_lookup(args.token))
    except Exception as e:
        print(f"could not reach the archive: {e}", file=sys.stderr)
        return 2

    report, code = render(receipt)
    print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
```

In the `Makefile`, add beside `verify-receipts`:

```makefile
resolve-dispute:
	# Resolve a dispute token into the receipt it names (TOKEN=<uuid>)
	PYTHONPATH=$(TOOL_PATH):$(CORE_PATH) uv run python tools/resolve_dispute.py $(TOKEN)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/test_resolve_dispute_tool.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: End-to-end check by hand**

The tool needs a live database, so this is a manual step rather than a test.
With Postgres up (`docker compose up -d db`), run a negotiation, take the
`dispute_token` from the response, and:

```bash
make resolve-dispute TOKEN=<the token>
```

Expected: the receipt prints with `verify ok`. An invented token prints
`not found` and exits 0.

- [ ] **Step 6: Run the whole core suite and lint**

```bash
PYTHONPATH=core/src:core/gen-proto:packages/aura-core/src:packages/aura-core/gen-proto uv run pytest core/tests/ -q
make lint
```

- [ ] **Step 7: Commit**

```bash
git add tools/resolve_dispute.py Makefile core/tests/test_resolve_dispute_tool.py
git commit -m "feat(tools): turn a cited dispute token into a verified receipt"
```

---

### Task 5: Say in the docs what is now true

**Files:**
- Modify: `docs/DECISION_RECEIPT.md` (§7 "Who actually reads one" — the paragraph beginning "The auditor's copy comes from the log")

**Interfaces:**
- Consumes: everything above. Produces no code interface.

- [ ] **Step 1: Correct the claim**

§7 currently says "The log line makes the log the store." That was true and is
now half the story — and the half it omits is the one that made this work
necessary. Replace the paragraph beginning "**This is the consumer that was
missing when step 6 was written off as unbuildable**" with:

```markdown
**This is the consumer that was missing when step 6 was written off as unbuildable** (§6). The
verifier had existed since the receipt did and ran only in tests, because no receipt was persisted
anywhere. The log line makes the log *a* store, and the tool makes it read.

**The log is not the durable store, and treating it as one was the gap.** It goes to a Loki outside
this repository whose retention is measured in days to weeks, so a dispute arriving a month after the
decision found nothing — the receipt had expired, signature and all. Every decision is now also
written to `decision_receipts` by the Connector on the C step, keyed by `dispute_token`, and
`make resolve-dispute TOKEN=…` turns a counterparty's citation into the receipt plus its verdict.

The write is fail-open, like the log line and for the same reason: reporting on a decision must never
take that decision down. The cost is that archive holes are possible and silent, so a failure emits
`receipt_record_failed` as its own event — an archive that sometimes never arrives is worse than one
that expires, because nothing announces it. The log line stays as an independent second path.
```

- [ ] **Step 2: Check nothing else still calls the log the store**

Run: `grep -n "the log the store\|log is the store" docs/DECISION_RECEIPT.md`
Expected: only the corrected passage. Fix any other occurrence the same way.

- [ ] **Step 3: Commit**

```bash
git add docs/DECISION_RECEIPT.md
git commit -m "docs: the log was never the durable store"
```
