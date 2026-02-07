import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher

from .bot import router
from .config import settings
from .effector import TelegramEffector
from .receptor import TelegramReceptor

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
    logger.info("Starting Aura Telegram Synapse", core_url=settings.core_url)

    # Initialize Bot
    bot = Bot(token=settings.token.get_secret_value())

    # Initialize Synapse Components
    receptor = TelegramReceptor(core_url=settings.core_url)
    effector = TelegramEffector(nats_url=settings.nats_url, bot=bot)

    # Initialize Dispatcher
    dp = Dispatcher()
    dp.include_router(router)

    # Start Effector (NATS listener) in background
    effector_task = asyncio.create_task(effector.start())

    try:
        # Pass receptor as dependency to handlers
        await dp.start_polling(bot, receptor=receptor)
    except asyncio.CancelledError:
        logger.info("Synapse stopped by user")
    except Exception as e:
        logger.error("Synapse crashed unexpectedly", error=str(e), exc_info=True)
    finally:
        effector_task.cancel()
        await effector.stop()
        await receptor.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
