import asyncio
import logging
import structlog
from aiogram import Dispatcher
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from config import settings
from bot import router
from setup import setup_bot

level = getattr(logging, settings.log_level.upper(), logging.INFO)
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.add_log_level, structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(level),
)
logger = structlog.get_logger()

async def nats_bloodstream_listener(metabolism) -> None:
    import nats
    nc = await nats.connect(settings.nats_url)
    sub = await nc.subscribe("aura.hive.events.>")
    bot_tracer = trace.get_tracer(__name__)
    async for msg in sub.messages:
        with bot_tracer.start_as_current_span("nats_event_received"):
            await metabolism.execute(msg.data, is_nats=True)

async def main() -> None:
    resource = Resource(attributes={SERVICE_NAME: "telegram-bot"})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    metabolism, registry, bot = await setup_bot()
    dp = Dispatcher()
    dp.include_router(router)
    nats_task = asyncio.create_task(nats_bloodstream_listener(metabolism))

    try:
        await dp.start_polling(bot, metabolism=metabolism)
    finally:
        nats_task.cancel()
        await registry.close()

if __name__ == "__main__":
    asyncio.run(main())
