from typing import TYPE_CHECKING, Any, cast

import dspy
import structlog
from aura_core import SkillProtocol, SkillRegistry, get_raw_key
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from prometheus_client import start_http_server
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hive.aggregator import HiveAggregator
from hive.connector import HiveConnector
from hive.generator import HiveGenerator
from hive.membrane import HiveMembrane
from hive.metabolism import MetabolicLoop
from hive.proteins.guard import GuardSkill
from hive.proteins.guard.engine import OutputGuard
from hive.proteins.persistence import PersistenceSkill
from hive.proteins.pulse import PulseSkill
from hive.proteins.pulse.engine import NatsProvider
from hive.proteins.reasoning import ReasoningSkill
from hive.proteins.reasoning.engine import get_embedding_model
from hive.proteins.telemetry import TelemetrySkill
from hive.proteins.telemetry.engine import init_telemetry
from hive.proteins.transaction import TransactionSkill
from hive.proteins.transaction.engine import (
    PriceConverter,
    SecretEncryption,
    SolanaProvider,
)
from hive.transformer import AuraTransformer

if TYPE_CHECKING:
    from hive.metabolism import MetabolicLoop

logger = structlog.get_logger("hive.cortex")


class HiveCell:
    """
    Cellular Assembly Unit (The Cell).
    Handles the initialization and wiring of all Hive components.
    """

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.registry = SkillRegistry()
        self.metabolism: MetabolicLoop | None = None
        self.market_service: Any = None

    async def build_organism(self) -> "MetabolicLoop":
        """
        Instantiate, bind, and wire all Proteins and Nucleotides.
        Returns a fully functional MetabolicLoop.
        """
        logger.info("assembling_hive_cell")

        # 0. Initialize Infrastructure (Telemetry, Tracing, Instrumentation)
        self._init_infrastructure()

        # 1. Initialize Proteins (Skills)
        await self._init_proteins()

        # 2. Initialize Nucleotides (ATCG-M)
        aggregator = HiveAggregator(registry=self.registry, settings=self.settings)
        transformer = AuraTransformer(registry=self.registry, settings=self.settings)

        # Market Service (Higher-order organ)
        market_service = None
        if self.settings.crypto.enabled:
            from hive.services.market import MarketService

            persistence = cast(SkillProtocol, self.registry.get("persistence"))
            transaction = cast(SkillProtocol, self.registry.get("transaction"))
            market_service = MarketService(
                persistence=persistence, transaction=transaction
            )
            self.market_service = market_service
            logger.info("market_service_wired")

        connector = HiveConnector(
            registry=self.registry,
            market_service=market_service,
            settings=self.settings,
        )
        generator = HiveGenerator(registry=self.registry, settings=self.settings)
        membrane = HiveMembrane(registry=self.registry)

        # 3. Form the Metabolic Loop
        self.metabolism = MetabolicLoop(
            aggregator=aggregator,
            transformer=transformer,
            connector=connector,
            generator=generator,
            membrane=membrane,
            registry=self.registry,
        )

        logger.info("organism_assembly_complete")
        return self.metabolism

    def _init_infrastructure(self) -> None:
        """Initialize telemetry, tracing, and gRPC instrumentation."""
        # 1. Start Prometheus metrics server
        try:
            metrics_port = self.settings.server.metrics_port
            start_http_server(metrics_port)
            logger.info("metrics_server_started", port=metrics_port)
        except Exception as e:
            logger.error("metrics_server_failed", error=str(e), exc_info=True)

        # 2. Initialize OpenTelemetry tracing
        service_name = self.settings.server.otel_service_name
        otel_endpoint = str(self.settings.server.otel_exporter_otlp_endpoint)

        init_telemetry(service_name, otel_endpoint)
        logger.info(
            "telemetry_initialized",
            service_name=service_name,
            endpoint=otel_endpoint,
        )

        # 3. Instrument gRPC server for distributed tracing
        GrpcInstrumentorServer().instrument()

        # 4. Instrument LangChain for LLM call tracing
        LangchainInstrumentor().instrument()

    async def _init_proteins(self) -> None:
        """Instantiate and bind all Proteins according to the Trinity Pattern."""

        # 1. Persistence
        engine = create_engine(str(self.settings.database.url))
        SessionLocal = sessionmaker(bind=engine)
        persistence = PersistenceSkill()
        persistence.bind(self.settings.database, (SessionLocal, engine))

        # 2. Pulse
        pulse = PulseSkill()
        pulse.bind(self.settings.server, NatsProvider(self.settings.server.nats_url))

        # 3. Reasoning
        lm = None
        embedder = None
        if self.settings.llm.model.lower() != "rule":
            lm = dspy.LM(self.settings.llm.model)
            embedder = get_embedding_model(get_raw_key(self.settings.llm.api_key))
        reasoning = ReasoningSkill()
        reasoning.bind(self.settings.llm, {"lm": lm, "embedder": embedder})

        # 4. Telemetry
        telemetry = TelemetrySkill()
        telemetry.bind(self.settings.server, None)

        # 5. Guard
        guard = GuardSkill()
        guard.bind(
            self.settings.safety, OutputGuard(safety_settings=self.settings.safety)
        )

        # 6. Transaction (Optional)
        transaction = None
        if self.settings.crypto.enabled:
            bundle = {
                "provider": SolanaProvider(
                    private_key_base58=get_raw_key(
                        self.settings.crypto.solana_private_key
                    ),
                    rpc_url=str(self.settings.crypto.solana_rpc_url),
                    usdc_mint=self.settings.crypto.solana_usdc_mint,
                ),
                "encryption": SecretEncryption(
                    get_raw_key(self.settings.crypto.secret_encryption_key)
                ),
                "converter": PriceConverter(),
            }
            transaction = TransactionSkill()
            transaction.bind(self.settings.crypto, bundle)

        # Register all in the SkillRegistry
        self.registry.register("persistence", persistence)
        self.registry.register("pulse", pulse)
        self.registry.register("reasoning", reasoning)
        self.registry.register("telemetry", telemetry)
        self.registry.register("guard", guard)
        if transaction:
            self.registry.register("transaction", transaction)

        # Initialize all proteins
        for name in self.registry.list_skills():
            skill = self.registry.get(name)
            if skill:
                success = await skill.initialize()
                if not success:
                    logger.error("protein_initialization_failed", protein=name)
                else:
                    # Optional post-initialization hook for protein-specific setup (e.g. DB init)
                    if hasattr(skill, "post_initialize") and callable(
                        skill.post_initialize
                    ):
                        await skill.post_initialize()


# Alias for backward compatibility during transition
HiveCortex = HiveCell
