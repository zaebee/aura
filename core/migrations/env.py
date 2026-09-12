import asyncio
import os
from logging.config import fileConfig

from alembic import context
from aura_hive.hive.proteins.persistence.engine import Base  # noqa: E402
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Read straight from the environment: building the full Settings would
# validate unrelated proteins (e.g. the LLM key), and the standalone
# DatabaseSettings model has no env support of its own. Migrations must
# run wherever a database URL exists.
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


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
