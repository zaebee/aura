import asyncio

import grpc
import nats
import structlog
from aiogram import Bot, Dispatcher
from aura_core import MetabolicLoop, SkillRegistry
from bot import router
from hive.aggregator import TelegramAggregator
from hive.connector import TelegramConnector
from hive.connector.proteins.aura_client import GRPCNegotiationClient
from hive.connector.proteins.telegram_api import TelegramProtein
from hive.generator import TelegramGenerator
from hive.transformer import TelegramTransformer
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config import settings

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
    resource = Resource(attributes={SERVICE_NAME: "telegram-bot"})
    provider = TracerProvider(resource=resource)

    # DNA Rule: FQDN for cross-namespace services
    otlp_endpoint = settings.otel_exporter_otlp_endpoint
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


async def main() -> None:
    # Setup OpenTelemetry
    setup_tracing()

    # Initialize NATS
    nc = None
    try:
        nc = await nats.connect(
            settings.nats_url,
            connect_timeout=5,
            reconnect_time_wait=2,
            max_reconnect_attempts=3,
        )
        logger.info("Connected to NATS", url=settings.nats_url)
    except (nats.errors.NoServersError, nats.errors.TimeoutError) as e:
        logger.error("Failed to connect to NATS (service might be down)", error=str(e))
    except Exception as e:
        logger.error("Unexpected error connecting to NATS", error=str(e))

    # Initialize Bot
    bot = Bot(token=settings.token.get_secret_value())

    # --- Provider Factories (Trinity Pattern) ---
    aura_channel = grpc.aio.insecure_channel(settings.core_url)

    # --- Skill Instantiation & Binding ---
    telegram_protein = TelegramProtein()
    telegram_protein.bind({}, bot)

    aura_protein = GRPCNegotiationClient()
    aura_protein.bind({"timeout": settings.negotiation_timeout}, aura_channel)

    # Initialize Skill Registry
    registry = SkillRegistry()
    registry.register("messenger", telegram_protein)
    registry.register("core_link", aura_protein)

    # Initialize Hive components
    aggregator = TelegramAggregator()
    transformer = TelegramTransformer()
    connector = TelegramConnector(registry)
    generator = TelegramGenerator(nats_client=nc)
    metabolism = MetabolicLoop(aggregator, transformer, connector, generator)

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
    except asyncio.CancelledError:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error("Bot crashed unexpectedly", error=str(e), exc_info=True)
    finally:
        await aura_protein.close()
        await bot.session.close()
        if nc:
            await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
