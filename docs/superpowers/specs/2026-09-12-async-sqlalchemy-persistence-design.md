# Async SQLAlchemy Persistence — Design

Date: 2026-09-12. Issue: #237. Approach: phased (B). Decisions: async-only
(including Alembic), full async + pgvector codec.

## Problem

The core service is async end-to-end except the database layer, which uses
synchronous SQLAlchemy (`Session`, `session.query`, `session.commit`) wrapped
in `asyncio.to_thread(...)` to avoid blocking the event loop. Every DB call
pays a thread hop, and the sync session API shapes the repository code.

Out of scope: `proteins/reasoning` (CPU/GPU-bound, threads are correct),
`proteins/discovery` (optional per #237). Skill Observation contracts do not
change — only the internals of the handlers.

## Phase 1 — Infra + codec probe

- Add `asyncpg` to `core/pyproject.toml` (pin against `sqlalchemy>=2.0.46`).
- `cortex.py` builds `create_async_engine` (`postgresql+asyncpg://`) next to
  the existing sync engine (dual period until Phase 3).
- Pool listener registers the pgvector codec (`pgvector.asyncpg.register_vector`)
  on raw connections. Loud failure at pool start if registration fails —
  fail-closed, no silent fallback. This is the phase's risk probe: codec
  first, repositories after.
- Alembic `env.py` goes async (`async_engine_from_config` +
  `await connection.run_sync(do_run_migrations)`). Offline mode unchanged.
  Verified by `upgrade head` from scratch plus a downgrade/upgrade round-trip
  against the test DB.
- Convert `ItemRepository` and `WalletRepository`: `async def`,
  `await session.execute(select(...))`, `await session.commit()`.
  `_get_session` returns `AsyncSession` from `async_sessionmaker`.
  Skill handlers for items/wallets `await` directly; the remaining ~14
  `to_thread` calls stay untouched.
- Tests: async tests for items + wallets on the real test DB
  (`AURA_DATABASE__URL` in conftest, same fixtures, async sessions);
  codec probe test (embedding write/read round-trip through an async
  session). `pytest-asyncio` is already a dependency.

Exit: codec + dimension-init proven under async; two repos green.

## Phase 2 — Rest of the layer

- `DealRepository` (create/get_by_id/get_by_memo; `SELECT FOR UPDATE`
  becomes `select(...).with_for_update()`, same lock semantics),
  `ReceiptRepository` (record/find_by_dispute_token),
  `items.search_by_vector` (same `cosine_distance` query via
  `await session.execute`).
- Remaining skill handlers drop `to_thread` for direct `await`.
- Done when `grep -rn to_thread proteins/persistence/` is empty
  (reasoning/discovery excluded by scope).

## Phase 3 — Cleanup

- Remove the sync engine from cortex. `bind()` provider tuple
  `(sessionmaker, Engine, redis)` becomes
  `(async_sessionmaker, AsyncEngine, redis)`. Delete sync leftovers.
- Done when there is one engine and full `core/tests` is green.

## Error handling

- No new semantics: handlers keep returning `Observation(success=False)`
  on failure; `GuardUnavailable`-style patterns are not copied over.
- Connection loss / pool timeouts behave as today (log + failure), no new
  retries in this change.
- Transactions: `async with session.begin()` where the repository owned the
  transaction; caller-owned boundaries are not moved, only awaited.

## Acceptance

1. Zero `asyncio.to_thread` in `proteins/persistence/`.
2. One engine (`create_async_engine` + `asyncpg`); `bind()` tuple updated.
3. Alembic runs through the async env on a clean DB.
4. Full `core/tests` green, ruff clean.
5. Cluster: core on the new image boots; `vector_search` answers
   (embedding round-trip against minikube prod DB).
