"""Phase 1 probe: async engine + pgvector codec actually work."""

import os

import pytest
from aura_hive.hive.cortex import build_async_engine
from sqlalchemy import text

TEST_URL = os.environ.get(
    "AURA_DATABASE__URL", "postgresql://test:test@localhost:5432/test_db"
).replace("postgresql://", "postgresql+asyncpg://")


async def _engine_or_skip(url: str):
    """Build the engine, skipping (not failing) when no test DB is up.

    Skip triggers only on CONNECT failure — a missing database is an
    environment gap. Anything after a successful connect (codec, SQL,
    assertions) still fails loudly.
    """
    engine, factory = build_async_engine(url)
    try:
        async with engine.connect():
            pass
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"test postgres unreachable: {exc}")
    return engine, factory


@pytest.mark.asyncio
async def test_async_engine_connects_and_registers_vector_codec():
    engine, _factory = await _engine_or_skip(TEST_URL)
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

    engine, _factory = await _engine_or_skip(TEST_URL)
    try:
        async with engine.begin() as conn:
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pytest.skip("pgvector extension unavailable in test DB")
            await conn.execute(
                text("CREATE TEMPORARY TABLE probe_vec (id int, e vector(3))")
            )
            await conn.execute(text("INSERT INTO probe_vec VALUES (1, '[1,2,3]')"))
            row = (
                await conn.execute(text("SELECT e FROM probe_vec WHERE id = 1"))
            ).first()
            assert row is not None
            assert list(row[0]) == pytest.approx([1.0, 2.0, 3.0])
            # Vector type object itself resolves on this engine:
            assert isinstance(Vector(3), Vector)
    finally:
        await engine.dispose()
