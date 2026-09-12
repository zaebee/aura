# Async Persistence Phase 1 (Infra + Codec Probe + items/wallets) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AsyncEngine + pgvector codec + async Alembic live alongside the sync engine, with ItemRepository and WalletRepository converted to async.

**Architecture:** Dual-engine transition. Cortex builds `create_async_engine` next to the existing sync engine and passes the async session factory as an optional 4th `bind()` element. Converted repos `await` directly; everything else keeps `to_thread`. Phases 2–3 (deals/receipts/vector, then sync removal) are separate plans after the codec probe lands.

**Tech Stack:** SQLAlchemy 2.0 (`create_async_engine`, `AsyncSession`, `async_sessionmaker`, `select()`), asyncpg, pgvector (`pgvector.asyncpg.register_vector`), Alembic async env, pytest-asyncio (explicit `@pytest.mark.asyncio`, strict mode — no auto mode configured).

**Spec:** `docs/superpowers/specs/2026-09-12-async-sqlalchemy-persistence-design.md`

## Global Constraints

- Python 3.12, SQLAlchemy `>=2.0.46` (from `core/pyproject.toml`).
- Skill Observation contracts do not change — same capability names, same success/error shapes.
- `proteins/reasoning` and `proteins/discovery` are out of scope and keep `to_thread`.
- Sync engine, sync `sessionmaker`, and sync Alembic path stay working until Phase 3.
- ruff check + format clean on every task; commit per task.

---

### Task 1: asyncpg dependency

**Files:**
- Modify: `core/pyproject.toml` (dependencies list, near line 19 `sqlalchemy>=2.0.46`)

**Interfaces:**
- Consumes: nothing.
- Produces: `asyncpg` importable in the core venv (needed by Tasks 2–4).

- [ ] **Step 1: Add the dependency**

```toml
"asyncpg>=0.29.0",
```

Place it alphabetically with the other DB deps in `core/pyproject.toml`.

- [ ] **Step 2: Lock and verify import**

Run: `uv lock && uv sync --frozen --package <core-package-name>`
(Find the exact package name at the top of `core/pyproject.toml`; if the workspace syncs as a whole, plain `uv sync --frozen` is fine.)

Run: `.venv/bin/python -c "import asyncpg; print(asyncpg.__version__)"`
Expected: version printed, no error.

- [ ] **Step 3: Commit**

```bash
git add core/pyproject.toml uv.lock
git commit -m "chore(persistence): add asyncpg for async SQLAlchemy (phase 1)"
```

---

### Task 2: Dual async engine + codec registration in cortex

**Files:**
- Modify: `core/src/aura_hive/hive/cortex.py` (imports ~lines 10–11, engine construction ~lines 197–201)

**Interfaces:**
- Consumes: `settings.database.url` (a `postgresql://` URL string).
- Produces: module-level helper `build_async_engine(url: str)` returning `(AsyncEngine, async_sessionmaker)`; cortex passes the session factory as 4th `bind()` element. Skill side (Task 5) consumes it.

- [ ] **Step 1: Write the failing probe test first**

Create `core/tests/test_persistence_async_engine.py`:

```python
"""Phase 1 probe: async engine + pgvector codec actually work."""

import os

import pytest
from sqlalchemy import text

from aura_hive.hive.cortex import build_async_engine

TEST_URL = os.environ.get(
    "AURA_DATABASE__URL", "postgresql://test:test@localhost:5432/test_db"
).replace("postgresql://", "postgresql+asyncpg://")


@pytest.mark.asyncio
async def test_async_engine_connects_and_registers_vector_codec():
    engine, _factory = build_async_engine(TEST_URL)
    try:
        async with engine.connect() as conn:
            # Proves the pool hands out working connections more than once
            # (pool growth path, where an unregistered fresh connection
            # would surface).
            await conn.execute(text("SELECT 1"))
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_vector_embedding_round_trip_through_async_session():
    """True codec proof: write and read back a vector through the engine.

    Skips (not fails) when the pgvector extension is absent from the test
    DB — that is an environment gap, not a code failure. Uses a TEMPORARY
    table so no test-DB schema is touched.
    """
    from pgvector.sqlalchemy import Vector

    engine, _factory = build_async_engine(TEST_URL)
    try:
        async with engine.begin() as conn:
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pytest.skip("pgvector extension unavailable in test DB")
            await conn.execute(
                text("CREATE TEMPORARY TABLE probe_vec (id int, e vector(3))")
            )
            await conn.execute(
                text("INSERT INTO probe_vec VALUES (1, '[1,2,3]')")
            )
            row = (
                await conn.execute(text("SELECT e FROM probe_vec WHERE id = 1"))
            ).first()
            assert row is not None
            assert list(row[0]) == pytest.approx([1.0, 2.0, 3.0])
            # Vector type object itself resolves on this engine:
            assert isinstance(Vector(3), Vector)
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest core/tests/test_persistence_async_engine.py -v`
Expected: FAIL with `ImportError` / `build_async_engine` not defined.

- [ ] **Step 3: Implement `build_async_engine`**

In `core/src/aura_hive/hive/cortex.py`, add imports:

```python
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
```

Add the builder (place near the top-level helpers):

```python
def _async_url(url: str) -> str:
    if "+asyncpg" in url:
        return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+asyncpg://", 1)
    return url


def build_async_engine(url: str) -> tuple[AsyncEngine, async_sessionmaker]:
    """Async engine plus session factory, with the pgvector codec registered.

    Registration runs per pooled connection: a `connect` listener calling
    the driver's purpose-built `dbapi_connection.run_async(register_vector)`
    (the SQLAlchemy-supported way to run awaitables inside pool event
    handlers — verified green by the probe test, including pool growth).
    """
    engine = create_async_engine(_async_url(url))

    @event.listens_for(engine.sync_engine, "connect")
    def _register_vector_codec(dbapi_connection: Any, _connection_record: Any) -> None:
        from pgvector.asyncpg import register_vector

        dbapi_connection.run_async(register_vector)

    return engine, async_sessionmaker(bind=engine, class_=AsyncSession)
```

Then extend the persistence wiring (~line 197):

```python
        # 1. Persistence
        engine = create_engine(str(self.settings.database.url))
        SessionLocal = sessionmaker(bind=engine)
        async_engine, AsyncSessionLocal = build_async_engine(
            str(self.settings.database.url)
        )
        redis_client = redis.from_url(str(self.settings.database.redis_url))
        persistence = PersistenceSkill()
        persistence.bind(
            self.settings.database,
            (SessionLocal, engine, redis_client, AsyncSessionLocal),
        )
```

- [ ] **Step 4: Run the probe test**

Run: `.venv/bin/python -m pytest core/tests/test_persistence_async_engine.py -v`
Expected: PASS. If the listener candidate fails (codec missing on second
connection), implement candidate B inside a `_get_async_session` factory in
`skill.py` (Task 5 area):

```python
async def _acquire_async_session(self) -> AsyncSession:
    session = self._async_provider()
    conn = await session.connection()
    raw = (await conn.get_raw_connection()).driver_connection
    if not conn.info.get("vector_registered"):
        from pgvector.asyncpg import register_vector

        await register_vector(raw)
        conn.info["vector_registered"] = True
    return session
```

and re-run until the probe passes. Only one candidate ships.

- [ ] **Step 5: Run the full suite (no regressions — nothing consumes the new engine yet)**

Run: `.venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`
Expected: same pass count as main (641 at time of writing).

- [ ] **Step 6: Commit**

```bash
git add core/src/aura_hive/hive/cortex.py core/tests/test_persistence_async_engine.py
git commit -m "feat(persistence): dual async engine with pgvector codec (phase 1)"
```

---

### Task 3: Async Alembic env

**Files:**
- Modify: `core/migrations/env.py` (full file, 72 lines — read it first)

**Interfaces:**
- Consumes: `config sqlalchemy.url` (rewritten to the `+asyncpg` driver), `Base.metadata` from `aura_hive.hive.proteins.persistence.engine` (unchanged).
- Produces: `alembic upgrade head` working through the async engine; offline mode unchanged.

- [ ] **Step 1: Rewrite `env.py` for async**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import engine_from_config
from sqlalchemy.ext.asyncio import async_engine_from_config

from aura_hive.hive.proteins.persistence.engine import Base  # noqa: E402

# URL straight from the environment (as implemented): the full Settings
# would validate unrelated proteins (LLM key), and standalone
# DatabaseSettings has no env support of its own.
db_url = os.environ.get("AURA_DATABASE__URL", "")
if not db_url:
    raise RuntimeError("AURA_DATABASE__URL is required to run migrations")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_url = db_url
if "+asyncpg" not in target_url:
    for prefix in ("postgresql://", "postgres://"):
        if target_url.startswith(prefix):
            target_url = target_url.replace(prefix, "postgresql+asyncpg://", 1)
            break
config.set_main_option("sqlalchemy.url", target_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL rendering only, no driver)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode through the async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_offline_entry() -> None:
    run_migrations_offline()


async def run_migrations_online_entry() -> None:
    await run_migrations_online()


if context.is_offline_mode():
    run_migrations_offline_entry()
else:
    asyncio.run(run_migrations_online_entry())
```

Note: `async_engine_from_config` reads the `sqlalchemy.url` main option set
above, so the driver rewrite must happen before this point in the file.

- [ ] **Step 2: Verify against the test DB (upgrade from scratch + round-trip)**

Run (needs postgres at `localhost:5432` with role `test`, as in CI):

```bash
AURA_DATABASE__URL=postgresql://test:test@localhost:5432/test_db .venv/bin/alembic -c core/alembic.ini downgrade base
AURA_DATABASE__URL=postgresql://test:test@localhost:5432/test_db .venv/bin/alembic -c core/alembic.ini upgrade head
AURA_DATABASE__URL=postgresql://test:test@localhost:5432/test_db .venv/bin/alembic -c core/alembic.ini downgrade -1
AURA_DATABASE__URL=postgresql://test:test@localhost:5432/test_db .venv/bin/alembic -c core/alembic.ini upgrade head
```

Expected: three version scripts apply in order
(`ea82989ed431` → `77450f9e9330` → `001_add_locked_deals`), no errors,
final `alembic_version` is the head. If no local postgres is available,
run the same four commands through `kubectl port-forward svc/aura-postgres`
against minikube (port 5433, user/password from chart values).

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`
Expected: all pass (migrations are not exercised by unit tests, but nothing
may break).

- [ ] **Step 4: Commit**

```bash
git add core/migrations/env.py
git commit -m "feat(persistence): async Alembic env (phase 1)"
```

---

### Task 4: WalletRepository goes async

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/persistence/wallet.py` (44 lines)
- Modify: `core/tests/test_persistence_wallet.py` (mock-based skill tests)

**Interfaces:**
- Consumes: async session factory `Callable[[], AsyncSession]` (same
  `self._get_session` attribute name on the repo is kept, but it now
  returns an `AsyncSession`; the factory is supplied by the skill — Task 6).
- Produces: `async def sanctify(wallet_address: str, asset_domain: str) -> None`,
  `async def is_sanctified(wallet_address: str | None) -> bool`.

- [ ] **Step 1: Rewrite the tests to async mocks (they fail first)**

In `core/tests/test_persistence_wallet.py`, replace the sync session mock
with an async one. Existing helper builds
`sessionmaker_mock = MagicMock(return_value=session_mock)` where the session
supports `__enter__`. Change the session mock to:

```python
session_mock = MagicMock()
session_mock.__aenter__ = AsyncMock(return_value=session_mock)
session_mock.__aexit__ = AsyncMock(return_value=False)
```

(`AsyncMock` comes from `unittest.mock`; add it to the existing
`from unittest.mock import MagicMock` import.)

Query chains stay `MagicMock` (they are not awaited — only `execute` is):

```python
session_mock.execute = AsyncMock()
```

Keep every existing assertion (`add`/`commit` call counts, Observation
shapes). The skill handler still wraps in `to_thread` at this point, so an
`AsyncMock` session inside `to_thread` still works — these tests must PASS
before the repo change (mock-shape check), then Task 6 switches the
handlers.

Run: `.venv/bin/python -m pytest core/tests/test_persistence_wallet.py -q`
Expected: PASS (mocks only).

- [ ] **Step 2: Convert the repository**

```python
"""WalletRepository — sanctified-wallet persistence, split out of PersistenceSkill.

Tracks which wallets have been "sanctified" for a given asset domain.
Async; the skill awaits these methods directly.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import SanctifiedWallet


class WalletRepository:
    """Sanctified-wallet lookups over an async session factory."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session = session_factory

    async def sanctify(self, wallet_address: str, asset_domain: str) -> None:
        async with self._session() as session:
            result = await session.execute(
                select(SanctifiedWallet).filter_by(
                    wallet_address=wallet_address
                )
            )
            if result.scalar_one_or_none() is None:
                session.add(
                    SanctifiedWallet(
                        wallet_address=wallet_address,
                        asset_domain=asset_domain,
                    )
                )
            await session.commit()

    async def is_sanctified(self, wallet_address: str | None) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(SanctifiedWallet).filter_by(
                    wallet_address=wallet_address
                )
            )
            return result.scalar_one_or_none() is not None
```

Note: `async with self._session()` requires the factory to return an
`AsyncSession` — supplied by the skill change in Task 6. The old sync
`session.query(...)` API is gone; `select()` + `execute()` + `scalar_*`
is the 2.0-style replacement.

- [ ] **Step 3: Run the wallet tests (they fail until Task 6 rewires the skill)**

Run: `.venv/bin/python -m pytest core/tests/test_persistence_wallet.py -q`
Expected: FAIL (handlers still `to_thread` sync-repo-shaped mocks around
async methods — e.g. coroutine never awaited). This is the expected
red state; Task 6 turns it green. Do NOT "fix" the tests to match —
fix the skill.

- [ ] **Step 4: Commit the repo + test change together**

```bash
git add core/src/aura_hive/hive/proteins/persistence/wallet.py core/tests/test_persistence_wallet.py
git commit -m "feat(persistence): WalletRepository goes async (phase 1, red)"
```

---

### Task 5: ItemRepository goes async (reads + upserts; vector search stays)

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/persistence/items.py` (all except `search_by_vector`)
- Modify: item-related tests (find them: `grep -rln "upsert_asset\|upsert_legacy\|get_by_id\|get_first" core/tests/` and convert the same mock shape as Task 4)

**Interfaces:**
- Consumes: async session factory (Task 6).
- Produces: `async def get_by_id`, `async def get_first`,
  `async def upsert_asset`, `async def upsert_legacy` with identical
  return shapes (`dict | None`, `None`, `None`). `search_by_vector`
  is explicitly UNTOUCHED (Phase 2).

- [ ] **Step 1: Convert the tests' mocks to async shape (pass first, as in Task 4)**

Run this first to enumerate every test file touching the item repo:

Run: `grep -rln "upsert_asset\|upsert_legacy\|get_by_id\|get_first\|search_by_vector" core/tests/`

For each file in the output EXCEPT vector-search-only tests (they stay
sync until Phase 2), apply the same transformation as Task 4 Step 1:
`__aenter__` / `__aexit__` via `AsyncMock`, `execute = AsyncMock()`, keep
all assertions.

Run the item tests. Expected: PASS.

- [ ] **Step 2: Convert the four methods**

Pattern for reads (shown for `get_by_id`; `get_first` is the same without
the filter):

```python
async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
    async with self._session() as session:
        result = await session.execute(
            select(InventoryItem).filter_by(id=item_id)
        )
        item = result.scalar_one_or_none()
        return ItemSchema.model_validate(item).model_dump() if item else None
```

Pattern for writes (shown for `upsert_legacy`; `upsert_asset` is converted
the same way — `select()` + `await session.execute(...)` + `await
session.commit()` — keeping its enzyme/tissue logic verbatim):

```python
async def upsert_legacy(self, params: dict[str, Any]) -> None:
    """Backward-compatible dictionary-based upsert."""
    item_id = params.get("id")
    async with self._session() as session:
        result = await session.execute(
            select(InventoryItem).filter_by(id=item_id)
        )
        item = result.scalar_one_or_none()
        if item:
            item.name = params.get("name", item.name)
            item.base_price = params.get("base_price", item.base_price)
            item.floor_price = params.get("floor_price", item.floor_price)
            item.meta = params.get("meta", item.meta)
            item.embedding = params.get("embedding", item.embedding)
        else:
            item = InventoryItem(
                id=item_id,
                name=params["name"],
                base_price=params["base_price"],
                floor_price=params["floor_price"],
                meta=params.get("meta", {}),
                embedding=params.get("embedding"),
            )
            session.add(item)
        await session.commit()
```

Update the module docstring: "Synchronous; callers wrap in
``asyncio.to_thread``" → "Async; the skill awaits these methods directly."

- [ ] **Step 3: Run item tests (red until Task 6, same as Task 4)**

Expected: FAIL. Do not adjust tests; Task 6 greens them.

- [ ] **Step 4: Commit**

```bash
git add core/src/aura_hive/hive/proteins/persistence/items.py <item-test-files-from-step-1>
git commit -m "feat(persistence): ItemRepository reads/upserts go async (phase 1, red)"
```

(Replace `<item-test-files-from-step-1>` with the actual paths enumerated
in Step 1.)

---

### Task 6: Skill awaits items/wallets; wire the async factory

**Files:**
- Modify: `core/src/aura_hive/hive/proteins/persistence/skill.py`
  (provider type ~lines 29–36/44/83–96, `_get_session`, handlers
  `_read_item_handler`, `_get_first_item`, `_upsert_item`,
  `_legacy_upsert_item`, `_sanctify_wallet`, `_is_wallet_sanctified`)

**Interfaces:**
- Consumes: 4th `bind()` element from Task 2 (optional
  `async_sessionmaker`, default `None` → converted handlers raise
  `RuntimeError("async_provider_not_initialized")` if absent, mirroring
  `_get_session`).
- Produces: six handlers awaiting repos directly; all other handlers
  byte-identical (still `to_thread`).

- [ ] **Step 1: Accept and expose the async factory**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
```

Provider type becomes
`tuple[sessionmaker, Engine, redis.Redis] | tuple[sessionmaker, Engine, redis.Redis, async_sessionmaker]`.
Simplest honest form:

```python
def bind(
    self,
    settings: DatabaseSettings,
    provider: tuple[sessionmaker, Engine, redis.Redis]
    | tuple[sessionmaker, Engine, redis.Redis, async_sessionmaker],
) -> None:
    self.settings = settings
    sync_factory, self.engine, self.redis, *rest = provider
    self.provider = sync_factory
    self._async_provider = rest[0] if rest else None
    if self.redis:
        self.cache = RedisCache(self.redis)
```

with `self._async_provider: async_sessionmaker | None = None` in
`__init__`, plus:

```python
def _get_async_session(self) -> AsyncSession:
    if not self._async_provider:
        raise RuntimeError("async_provider_not_initialized")
    return self._async_provider()
```

Repos are constructed with the async factory:

```python
self._items = ItemRepository(self._get_async_session)
self._wallets = WalletRepository(self._get_async_session)
```

(`DealRepository`/`ReceiptRepository` keep `self._get_session` until
Phase 2.)

- [ ] **Step 2: Convert the six handlers (mechanical `await`)**

```python
result = await self._items.get_by_id(item_id)          # was to_thread
result = await self._items.get_first()                 # was to_thread
await self._items.upsert_asset(asset)                  # was to_thread
await self._items.upsert_legacy(params)                # was to_thread
await self._wallets.sanctify(wallet_address, asset_domain)  # was to_thread
sanctified = await self._wallets.is_sanctified(wallet_address)  # was to_thread
```

Nothing else in those handlers changes (Observation shapes identical).

- [ ] **Step 3: Run the red tests green + full suite**

Run: `.venv/bin/python -m pytest core/tests/test_persistence_wallet.py core/tests/test_persistence_async_engine.py -q`
Expected: PASS.

Run: `.venv/bin/python -m pytest core/tests/ -q -p no:cacheprovider`
Expected: all pass (same count as main plus the new probe test).

Run: `.venv/bin/ruff check <touched files> && .venv/bin/ruff format --check <touched files>`
Expected: clean; format what ruff flags.

- [ ] **Step 4: Commit**

```bash
git add core/src/aura_hive/hive/proteins/persistence/skill.py
git commit -m "feat(persistence): skill awaits items/wallets over async sessions (phase 1)"
```

Phase 1 exit check: `grep -c asyncio.to_thread
core/src/aura_hive/hive/proteins/persistence/skill.py` shows only the
deals/receipts/vector/metabolic handlers (10 remaining); items/wallets
paths are `await`-only; probe + wallet + item tests green.
