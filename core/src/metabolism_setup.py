import dspy
from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aura_core import SkillRegistry, get_raw_key
from hive.aggregator import HiveAggregator
from hive.connector import HiveConnector
from hive.generator import HiveGenerator
from hive.membrane import HiveMembrane
from hive.metabolism import MetabolicLoop
from hive.proteins.guard import GuardSkill
from hive.proteins.guard.enzymes.guard_logic import OutputGuard
from hive.proteins.persistence import PersistenceSkill
from hive.proteins.pulse import PulseSkill
from hive.proteins.pulse.enzymes.pulse_broker import NatsProvider
from hive.proteins.reasoning import ReasoningSkill
from hive.proteins.reasoning.enzymes.engine import get_embedding_model
from hive.proteins.telemetry import TelemetrySkill
from hive.proteins.transaction import TransactionSkill
from hive.proteins.transaction.enzymes.solana import (
    PriceConverter,
    SecretEncryption,
    SolanaProvider,
)
from hive.services.market import MarketService
from config import settings

async def setup_metabolism() -> tuple[MetabolicLoop, SkillRegistry, MarketService | None]:
    # Initialize Skills (Proteins)
    registry = SkillRegistry()

    # --- Provider Factories (Trinity Pattern) ---
    engine = create_engine(str(settings.database.url))
    SessionLocal = sessionmaker(bind=engine)
    nats_provider = NatsProvider(settings.server.nats_url)

    transaction_bundle = {}
    if settings.crypto.enabled:
        transaction_bundle = {
            "provider": SolanaProvider(
                private_key_base58=get_raw_key(settings.crypto.solana_private_key),
                rpc_url=str(settings.crypto.solana_rpc_url),
                usdc_mint=settings.crypto.solana_usdc_mint,
            ),
            "encryption": SecretEncryption(
                get_raw_key(settings.crypto.secret_encryption_key)
            ),
            "converter": PriceConverter(),
        }

    lm = None
    embedder = None
    if settings.llm.model.lower() != "rule":
        lm = dspy.LM(settings.llm.model)
        embedder = get_embedding_model(get_raw_key(settings.llm.api_key))
    reasoning_provider = {"lm": lm, "embedder": embedder}
    guard_provider = OutputGuard(safety_settings=settings.safety)

    # --- Skill Instantiation & Binding ---
    persistence_protein = PersistenceSkill()
    persistence_protein.bind(settings.database, (SessionLocal, engine))

    pulse_protein = PulseSkill()
    pulse_protein.bind(settings.server, nats_provider)

    reasoning_protein = ReasoningSkill()
    reasoning_protein.bind(settings.llm, reasoning_provider)

    telemetry_protein = TelemetrySkill()
    telemetry_protein.bind(settings.server, None)

    guard_protein = GuardSkill()
    guard_protein.bind(settings.safety, guard_provider)

    transaction_protein = None
    if settings.crypto.enabled:
        transaction_protein = TransactionSkill()
        transaction_protein.bind(settings.crypto, transaction_bundle)

    # Register in registry
    registry.register("persistence", persistence_protein)
    if transaction_protein:
        registry.register("transaction", transaction_protein)
    registry.register("reasoning", reasoning_protein)
    registry.register("telemetry", telemetry_protein)
    registry.register("pulse", pulse_protein)
    registry.register("guard", guard_protein)

    # Initialize Skills
    await persistence_protein.initialize()
    await pulse_protein.initialize()
    await reasoning_protein.initialize()
    await telemetry_protein.initialize()
    await guard_protein.initialize()
    if transaction_protein:
        await transaction_protein.initialize()

    await persistence_protein.execute("init_db", {})

    # Initialize Nucleotides
    aggregator = HiveAggregator(registry=registry, settings=settings)
    from hive.transformer import AuraTransformer
    transformer = AuraTransformer(registry=registry, settings=settings)

    market_service = None
    if transaction_protein:
        market_service = MarketService(
            persistence=persistence_protein, transaction=transaction_protein
        )

    connector = HiveConnector(
        registry=registry, market_service=market_service, settings=settings
    )
    generator = HiveGenerator(registry=registry)
    membrane = HiveMembrane(registry=registry)

    metabolism = MetabolicLoop(
        aggregator=aggregator,
        transformer=transformer,
        connector=connector,
        generator=generator,
        membrane=membrane,
    )

    return metabolism, registry, market_service
