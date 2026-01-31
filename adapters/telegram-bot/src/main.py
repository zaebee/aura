import asyncio
import os

import structlog
import nats
from aiogram import Bot, Dispatcher

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from src.bot import router
from src.client import GRPCNegotiationClient
from src.config import settings
from src.hive.aggregator import TelegramAggregator
from src.hive.transformer import TelegramTransformer
from src.hive.connector import TelegramConnector
from src.hive.generator import TelegramGenerator
from src.hive.metabolism import TelegramMetabolism

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()

def setup_tracing() -> None:
    resource = Resource(attributes={
        SERVICE_NAME: "telegram-bot"
    })
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

async def main() -> None:
    # Setup OpenTelemetry
    setup_tracing()

    # Initialize NATS
    nc = None
    try:
        nats_url = os.getenv("NATS_URL", "nats://nats:4222")
        nc = await nats.connect(nats_url)
        logger.info("Connected to NATS", url=nats_url)
    except Exception as e:
        logger.error("Failed to connect to NATS", error=str(e))

    # Initialize gRPC client
    client = GRPCNegotiationClient(settings.core_url)

    # Initialize Bot
    bot = Bot(token=settings.token.get_secret_value())

    # Initialize Hive components
    aggregator = TelegramAggregator()
    transformer = TelegramTransformer()
    connector = TelegramConnector(bot, client)
    generator = TelegramGenerator(nats_client=nc)
    metabolism = TelegramMetabolism(aggregator, transformer, connector, generator)

    # Initialize Dispatcher
    dp = Dispatcher()

    # Register router
    dp.include_router(router)

    logger.info(
        "Starting Aura Telegram Bot with ATCG Hive pattern",
        core_url=settings.core_url,
    )

    try:
        # Pass metabolism as dependency to handlers
        await dp.start_polling(bot, metabolism=metabolism)
    except Exception as e:
        logger.error("Bot crashed", error=str(e))
    finally:
        await client.close()
        await bot.session.close()
        if nc:
            await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
