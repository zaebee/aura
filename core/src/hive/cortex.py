import dspy
import structlog
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aura_core import SkillRegistry, get_raw_key

from hive.aggregator import HiveAggregator
from hive.connector import HiveConnector
from hive.generator import HiveGenerator
from hive.membrane import HiveMembrane
from hive.metabolism import MetabolicLoop
from hive.transformer import AuraTransformer

# Proteins (Skills)
from hive.proteins.persistence import PersistenceSkill
from hive.proteins.pulse import PulseSkill
from hive.proteins.pulse.pulse_broker import NatsProvider
from hive.proteins.reasoning import ReasoningSkill
from hive.proteins.reasoning.reasoning_engine import get_embedding_model
from hive.proteins.telemetry import TelemetrySkill
from hive.proteins.transaction import TransactionSkill
from hive.proteins.transaction.solana import (
    PriceConverter,
    SecretEncryption,
    SolanaProvider,
)
from hive.proteins.guard import GuardSkill
from hive.proteins.guard.guard_logic import OutputGuard

# Services
from hive.services.market import MarketService

logger = structlog.get_logger(__name__)

class HiveCortex:
    """
    Cellular Assembly Unit (The Cell).
    Orchestrates the instantiation and wiring of the Hive Organism.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.registry = SkillRegistry()
        self.market_service: MarketService | None = None
        self.is_healthy = False

    async def build_organism(self) -> MetabolicLoop:
        """
        Synthesize the Metabolic Loop (The Organism).
        1. Initialize SkillRegistry.
        2. Bind and initialize all Proteins.
        3. Instantiate Nucleotides.
        4. Return fully wired MetabolicLoop.
        """
        logger.info("organism_synthesis_started")

        # --- 1. Provider Factories (Trinity Pattern) ---

        # Persistence Provider
        engine = create_engine(str(self.settings.database.url))
        SessionLocal = sessionmaker(bind=engine)

        # Pulse Provider
        nats_provider = NatsProvider(self.settings.server.nats_url)

        # Transaction Provider (if enabled)
        transaction_bundle = {}
        if self.settings.crypto.enabled:
            transaction_bundle = {
                "provider": SolanaProvider(
                    private_key_base58=get_raw_key(self.settings.crypto.solana_private_key),
                    rpc_url=str(self.settings.crypto.solana_rpc_url),
                    usdc_mint=self.settings.crypto.solana_usdc_mint,
                ),
                "encryption": SecretEncryption(
                    get_raw_key(self.settings.crypto.secret_encryption_key)
                ),
                "converter": PriceConverter(),
            }

        # Reasoning Provider
        lm = None
        embedder = None
        if self.settings.llm.model.lower() != "rule":
            lm = dspy.LM(self.settings.llm.model)
            embedder = get_embedding_model(get_raw_key(self.settings.llm.api_key))
        reasoning_provider = {"lm": lm, "embedder": embedder}

        # Guard Provider
        guard_provider = OutputGuard(safety_settings=self.settings.safety)

        # --- 2. Skill Instantiation & Binding ---

        persistence_protein = PersistenceSkill()
        persistence_protein.bind(self.settings.database, (SessionLocal, engine))

        pulse_protein = PulseSkill()
        pulse_protein.bind(self.settings.server, nats_provider)

        reasoning_protein = ReasoningSkill()
        reasoning_protein.bind(self.settings.llm, reasoning_provider)

        telemetry_protein = TelemetrySkill()
        telemetry_protein.bind(self.settings.server, None)

        guard_protein = GuardSkill()
        guard_protein.bind(self.settings.safety, guard_provider)

        transaction_protein = None
        if self.settings.crypto.enabled:
            transaction_protein = TransactionSkill()
            transaction_protein.bind(self.settings.crypto, transaction_bundle)

        # Register in registry
        self.registry.register("persistence", persistence_protein)
        if transaction_protein:
            self.registry.register("transaction", transaction_protein)
        self.registry.register("reasoning", reasoning_protein)
        self.registry.register("telemetry", telemetry_protein)
        self.registry.register("pulse", pulse_protein)
        self.registry.register("guard", guard_protein)

        # --- 3. Initialize Skills ---
        # Note: initialization logic is preserved from main.py
        if await persistence_protein.initialize():
            await persistence_protein.execute("init_db", {})
            logger.info("persistence_verified")
            self.is_healthy = True
        else:
            logger.error("persistence_verification_failed")
            self.is_healthy = False

        await pulse_protein.initialize()
        await reasoning_protein.initialize()
        await telemetry_protein.initialize()
        await guard_protein.initialize()
        if transaction_protein:
            await transaction_protein.initialize()

        # --- 4. Initialize Nucleotides & Services ---

        aggregator = HiveAggregator(registry=self.registry, settings=self.settings)
        transformer = AuraTransformer(registry=self.registry, settings=self.settings)

        if transaction_protein:
            self.market_service = MarketService(
                persistence=persistence_protein, transaction=transaction_protein
            )
            logger.info("market_service_initialized")

        connector = HiveConnector(
            registry=self.registry, market_service=self.market_service, settings=self.settings
        )
        generator = HiveGenerator(registry=self.registry)
        membrane = HiveMembrane(registry=self.registry)

        metabolism = MetabolicLoop(
            aggregator=aggregator,
            transformer=transformer,
            connector=connector,
            generator=generator,
            membrane=membrane,
            registry=self.registry,
        )

        logger.info("organism_synthesis_complete")
        return metabolism
