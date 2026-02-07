import asyncio
import logging
import os

import nats
import structlog
from aiogram import Bot, Dispatcher
from effector import TelegramEffector
from hive.cortex import HiveCell
from receptor import TelegramReceptor
from synapse_settings import settings as tg_settings
from translator import TelegramTranslator

from config import Settings as CoreSettings

# Setup logging
level = getattr(logging, tg_settings.log_level.upper(), logging.INFO)
log_format = os.getenv("AURA_LOG_FORMAT", "json").lower()
renderer = (
    structlog.dev.ConsoleRenderer()
    if log_format == "console"
    else structlog.processors.JSONRenderer()
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        renderer,
    ],
    wrapper_class=structlog.make_filtering_bound_logger(level),
)
logger = structlog.get_logger("telegram-bot")


async def main() -> None:
    logger.info(
        "starting_telegram_synapse", prefix=tg_settings.model_config.get("env_prefix")
    )

    # 1. Initialize NATS Bloodstream
    nc = None
    try:
        nc = await nats.connect(
            tg_settings.nats_url,
            connect_timeout=5,
            reconnect_time_wait=2,
            max_reconnect_attempts=60,
        )
        logger.info("connected_to_nats", url=tg_settings.nats_url)
    except Exception as e:
        logger.error("nats_connection_failed", error=str(e))
        # We continue as the bot might still function for non-bloodstream tasks,
        # but Effector will fail.

    # 2. Initialize the "Cell" (Core Metabolism)
    # We load CoreSettings which will pick up AURA_ prefixed env vars
    core_config = CoreSettings()
    cell = HiveCell(core_config)
    metabolism = await cell.build_organism()
    logger.info("metabolism_initialized_in_process")

    # 3. Initialize Bot and Translator
    bot = Bot(token=tg_settings.token.get_secret_value())
    translator = TelegramTranslator()

    # 4. Initialize Receptor (Inbound)
    receptor = TelegramReceptor(metabolism, translator)

    # 5. Initialize Effector (Outbound)
    effector = None
    if nc:
        effector = TelegramEffector(nc, bot, translator)

    # 6. Setup Aiogram Dispatcher
    dp = Dispatcher()
    dp.include_router(receptor.router)

    logger.info("synapse_ready", core_url=tg_settings.core_url)

    tasks = []

    # Start Effector background task
    if effector:
        tasks.append(asyncio.create_task(effector.run()))
        logger.info("effector_task_started")

    # Start Bot Polling
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error("bot_polling_failed", error=str(e))
    finally:
        for task in tasks:
            task.cancel()
        if nc:
            await nc.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
