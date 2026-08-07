import asyncio
import logging
import os

import nats
import structlog
from aiogram import Bot, Dispatcher

from .effector import TelegramEffector
from .grpc_adapter import GrpcAdapter
from .health import start_health_server
from .health import state as health_state
from .nats_adapter import NatsAdapter
from .receptor import TelegramReceptor
from .synapse_settings import settings as tg_settings
from .translator import TelegramTranslator

# Setup logging
level = (
    logging.DEBUG
    if tg_settings.debug
    else getattr(logging, tg_settings.log_level.upper(), logging.INFO)
)
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
    logger.debug(
        "synapse_settings",
        nats_url=tg_settings.nats_url,
        signal_subject=tg_settings.signal_subject,
        log_level=tg_settings.log_level,
        negotiation_timeout=tg_settings.negotiation_timeout,
        webhook_domain=tg_settings.webhook_domain,
        otel_endpoint=tg_settings.otel_exporter_otlp_endpoint,
        log_format=log_format,
        debug=tg_settings.debug,
    )

    # 1. Connect to NATS (required — bot communicates with core via NATS)
    nc = None
    try:
        logger.debug("connecting_to_nats", url=tg_settings.nats_url)
        nc = await nats.connect(
            tg_settings.nats_url,
            connect_timeout=5,
            reconnect_time_wait=2,
            max_reconnect_attempts=60,
        )
        logger.info("connected_to_nats", url=tg_settings.nats_url)
    except Exception as e:
        logger.error("nats_connection_failed", error=str(e))

    if not nc:
        logger.critical(
            "nats_required", reason="Cannot operate without NATS connection"
        )
        return

    # 2. Initialize NATS Adapter (replaces in-process core metabolism)
    adapter = NatsAdapter(
        nc=nc,
        signal_subject=tg_settings.signal_subject,
        timeout=tg_settings.negotiation_timeout,
    )
    logger.info("nats_adapter_initialized", signal_subject=tg_settings.signal_subject)

    # 3. Initialize Bot and Translator
    bot = Bot(token=tg_settings.token.get_secret_value())
    translator = TelegramTranslator()
    logger.debug("bot_and_translator_initialized")

    # 4. Initialize gRPC Adapter
    grpc_adapter = GrpcAdapter(tg_settings.core_grpc_url)
    logger.info("grpc_adapter_initialized", url=tg_settings.core_grpc_url)

    # 5. Initialize Receptor (Inbound: Telegram -> NATS/gRPC -> Core)
    receptor = TelegramReceptor(adapter, translator, grpc_adapter=grpc_adapter)
    logger.debug("receptor_initialized")

    # 6. Initialize Effector (Outbound: Core -> NATS -> Telegram)
    effector = TelegramEffector(nc, bot, translator)
    logger.debug("effector_initialized")

    # 7. Setup Aiogram Dispatcher
    dp = Dispatcher()
    dp.include_router(receptor.router)
    logger.debug("dispatcher_configured", routers=1)

    logger.info("synapse_ready", nats_url=tg_settings.nats_url)

    # 8. Start Health probe server
    health_runner = await start_health_server(tg_settings.health_port)
    logger.info("health_server_started", port=tg_settings.health_port)

    # Mark probe state
    health_state.nats_connected = True
    health_state.bot_polling = True

    tasks = []

    # Start Effector background task
    tasks.append(asyncio.create_task(effector.run()))
    logger.info("effector_task_started")

    # Start Bot Polling
    logger.debug("starting_bot_polling")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error("bot_polling_failed", error=str(e))
    finally:
        logger.debug("shutting_down", active_tasks=len(tasks))
        health_state.bot_polling = False
        for task in tasks:
            task.cancel()
        await nc.close()
        await grpc_adapter.close()
        await bot.session.close()
        logger.debug("shutdown_complete")
        await health_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
