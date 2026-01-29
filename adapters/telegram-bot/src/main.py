import asyncio
import structlog
from aiogram import Bot, Dispatcher
from src.config import settings
from src.handlers import router
from src.client import AuraClient

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


async def main():
    # Initialize gRPC client
    client = AuraClient(settings.core_grpc_url)

    # Initialize Bot and Dispatcher
    bot = Bot(token=settings.bot_token.get_secret_value())
    dp = Dispatcher()

    # Register router and pass client to handlers
    dp.include_router(router)

    logger.info(
        "Starting Aura Telegram Bot",
        core_grpc_url=settings.core_grpc_url,
        use_polling=settings.use_polling
    )

    try:
        if settings.use_polling:
            # We pass the client as a keyword argument to be available in handlers
            await dp.start_polling(bot, client=client)
        else:
            logger.error("Webhook mode not implemented yet.")
    except Exception as e:
        logger.error("Bot crashed", error=str(e))
    finally:
        await client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
