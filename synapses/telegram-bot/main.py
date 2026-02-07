import asyncio
import logging
import nats
import structlog
import grpc
from aiogram import Bot, Dispatcher
from aura_core import SkillRegistry
from receptor import router
from effector import TelegramEffector
from client import GRPCNegotiationClient
from config import settings

# Setup logging
level = getattr(logging, settings.log_level.upper(), logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(level),
)
logger = structlog.get_logger()

async def main() -> None:
    # Initialize NATS
    nc = await nats.connect(settings.nats_url)
    logger.info("Connected to NATS", url=settings.nats_url)

    # Initialize Bot
    bot = Bot(token=settings.token.get_secret_value())

    # Initialize Effector
    effector = TelegramEffector(bot)

    # --- Metabolism Connection ---
    # Connect to the core's gRPC service
    metabolism = GRPCNegotiationClient(
        core_url=settings.core_url,
        timeout=settings.negotiation_timeout
    )

    # Initialize Dispatcher
    dp = Dispatcher()
    dp.include_router(router)

    # --- Effector: NATS Bloodstream Listener ---
    async def nats_bloodstream_listener() -> None:
        sub = await nc.subscribe("aura.hive.events.>")
        logger.info("nats_bloodstream_subscribed", subject="aura.hive.events.>")
        async for msg in sub.messages:
            await effector.emit(msg.data)

    # Start NATS listener in background
    nats_task = asyncio.create_task(nats_bloodstream_listener())

    try:
        # Pass metabolism as dependency to handlers
        await dp.start_polling(bot, metabolism=metabolism)
    finally:
        nats_task.cancel()
        await metabolism.close()
        await bot.session.close()
        await nc.close()

if __name__ == "__main__":
    asyncio.run(main())
