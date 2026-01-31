import asyncio

import structlog
from aiogram import Bot, Dispatcher

from src.bot import router
from src.client import GRPCNegotiationClient
from src.config import settings

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


async def main() -> None:
    # Initialize gRPC client
    client = GRPCNegotiationClient(settings.core_url)

    # Initialize Bot and Dispatcher
    bot = Bot(token=settings.token.get_secret_value())
    dp = Dispatcher()

    # Register router
    dp.include_router(router)

    logger.info(
        "Starting Aura Telegram Bot",
        core_url=settings.core_url,
    )

    try:
        # Pass client as dependency to handlers
        await dp.start_polling(bot, client=client)
    except Exception as e:
        logger.error("Bot crashed", error=str(e))
    finally:
        await client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
