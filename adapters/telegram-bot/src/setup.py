import grpc
import nats
from aiogram import Bot
from aura_core import MetabolicLoop, SkillRegistry
from hive.aggregator import TelegramAggregator
from hive.connector import TelegramConnector
from hive.connector.proteins.aura_client import GRPCNegotiationClient
from hive.connector.proteins.telegram_api import TelegramProtein
from hive.generator import TelegramGenerator
from hive.proteins.pulse import PulseSkill
from hive.proteins.pulse.enzymes.pulse_broker import NatsProvider
from hive.proteins.telemetry import TelemetrySkill
from hive.transformer import TelegramTransformer
from config import settings

async def setup_bot() -> tuple[MetabolicLoop, SkillRegistry, Bot]:
    nc = await nats.connect(settings.nats_url)
    bot = Bot(token=settings.token.get_secret_value())
    aura_channel = grpc.aio.insecure_channel(settings.core_url)
    nats_provider = NatsProvider(settings.nats_url)

    telegram_protein = TelegramProtein()
    telegram_protein.bind({}, bot)
    aura_protein = GRPCNegotiationClient()
    aura_protein.bind({"timeout": settings.negotiation_timeout}, aura_channel)
    pulse_protein = PulseSkill()
    pulse_protein.bind(settings, nats_provider)
    telemetry_protein = TelemetrySkill()
    telemetry_protein.bind(settings, None)

    registry = SkillRegistry()
    registry.register("messenger", telegram_protein)
    registry.register("core_link", aura_protein)
    registry.register("pulse", pulse_protein)
    registry.register("telemetry", telemetry_protein)

    await pulse_protein.initialize()
    await telemetry_protein.initialize()

    aggregator = TelegramAggregator()
    transformer = TelegramTransformer()
    connector = TelegramConnector(registry)
    generator = TelegramGenerator(registry=registry, settings=settings)
    metabolism = MetabolicLoop(aggregator, transformer, connector, generator)

    return metabolism, registry, bot
