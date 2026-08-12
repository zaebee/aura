from typing import TYPE_CHECKING, Any, cast

import dspy
import redis.asyncio as redis
import structlog
from aura_core import SkillProtocol, SkillRegistry, get_raw_key
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from prometheus_client import start_http_server
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aura_hive.config.attestation import AttestationSettings
from aura_hive.hive.aggregator import HiveAggregator
from aura_hive.hive.connector import HiveConnector
from aura_hive.hive.generator import HiveGenerator
from aura_hive.hive.membrane import HiveMembrane
from aura_hive.hive.metabolism import MetabolicLoop
from aura_hive.hive.metabolism.security import AuditSigner
from aura_hive.hive.proteins.attestation import AttestationEngine, AttestationSkill
from aura_hive.hive.proteins.blockchain_data.skill import GoldRushSkill
from aura_hive.hive.proteins.coherence import CoherenceSkill
from aura_hive.hive.proteins.discovery import DiscoverySkill
from aura_hive.hive.proteins.guard import GuardSkill
from aura_hive.hive.proteins.guard.engine import OutputGuard
from aura_hive.hive.proteins.kinetic.engine import KineticEngine
from aura_hive.hive.proteins.kinetic.skill import KineticSkill
from aura_hive.hive.proteins.perception import PerceptionSkill
from aura_hive.hive.proteins.perception.engine import PerceptionEngine
from aura_hive.hive.proteins.persistence import PersistenceSkill
from aura_hive.hive.proteins.pulse import PulseSkill
from aura_hive.hive.proteins.pulse.engine import NatsProvider
from aura_hive.hive.proteins.reasoning import ReasoningSkill
from aura_hive.hive.proteins.reasoning.engine import get_embedding_model
from aura_hive.hive.proteins.telemetry import TelemetrySkill
from aura_hive.hive.proteins.telemetry.engine import init_telemetry
from aura_hive.hive.proteins.transaction import TransactionSkill
from aura_hive.hive.proteins.transaction.engine import (
    EVMProvider,
    PriceConverter,
    SecretEncryption,
)
from aura_hive.hive.proteins.transaction.solana_engine import SolanaProvider
from aura_hive.hive.transformer import AuraTransformer

if TYPE_CHECKING:
    from aura_hive.hive.metabolism import MetabolicLoop

logger = structlog.get_logger("hive.cortex")


def build_attestation(
    private_key_hex: str, settings: AttestationSettings
) -> AttestationSkill | None:
    """
    The attestation protein, or nothing.

    Registered on key presence rather than on a feature flag. A flag that can
    be set true without a key is another "enabled but not working" state, and
    that is exactly what this replaces: signing used to be gated on
    `crypto.enabled`, a flag about payment locks, which was false everywhere
    and would not have signed anything if it were true, because no EVM key was
    ever plumbed into the deployment.

    A module-level function rather than a method, so the decision can be tested
    without booting a cell.
    """
    # Stripped before anything looks at it. A secret written with `echo` rather
    # than `printf` carries a trailing newline, which is the most common way a
    # real key arrives malformed — and without this it is indistinguishable
    # from a corrupt one, so the cell refuses to boot over an invisible
    # character.
    private_key_hex = private_key_hex.strip()

    if not private_key_hex:
        logger.info("attestation_disabled_no_key")
        return None

    try:
        engine = AttestationEngine(private_key_hex)
    except Exception as exc:
        # Deliberately fatal. The alternatives are booting while believing we
        # attest, or failing per-decision — and a deployment that cannot read
        # its own signing key is the "enabled but not working" state this
        # protein exists to make unrepresentable.
        #
        # The setting is named because the operator has to know which one is
        # wrong; the value never is, and the underlying libraries do not echo
        # it either ("Non-hexadecimal digit found", "must be exactly 32 bytes").
        raise ValueError(
            f"AURA_ATTESTATION__PRIVATE_KEY is set but unusable: {exc}"
        ) from exc

    skill = AttestationSkill()
    skill.bind(settings, engine)
    # The address, never the key. This is the only place a deployment states
    # which signer its receipts will recover to.
    logger.info("attestation_signer_ready", address=engine.address)
    return skill


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
            from aura_hive.hive.services.market import MarketService

            persistence = cast(SkillProtocol, self.registry.get("persistence"))
            transaction = cast(SkillProtocol, self.registry.get("transaction"))
            pulse = cast(SkillProtocol, self.registry.get("pulse"))
            market_service = MarketService(
                persistence=persistence, transaction=transaction, pulse=pulse
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
        redis_client = redis.from_url(str(self.settings.database.redis_url))
        persistence = PersistenceSkill()
        persistence.bind(self.settings.database, (SessionLocal, engine, redis_client))

        # 2. Pulse
        signer = None
        if self.settings.server.audit_signing_key:
            signer = AuditSigner(self.settings.server.audit_signing_key)
        pulse = PulseSkill()
        pulse.bind(
            self.settings.server,
            NatsProvider(self.settings.server.nats_url, signer=signer),
        )

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

        # 6. Perception
        perception = PerceptionSkill()
        # 10. Coherence (UHM PoC)
        coherence = CoherenceSkill()
        coherence.bind(self.settings, None)
        self.registry.register("coherence", coherence)

        perception.bind(
            self.settings.perception,
            PerceptionEngine(
                ollama_url=self.settings.perception.remote_ollama_url
                or self.settings.perception.ollama_url,
                model=self.settings.perception.model,
            ),
        )

        # 7. Discovery
        discovery = DiscoverySkill()
        discovery.bind(self.settings.discovery, {"lm": lm})

        # 8. Kinetic
        kinetic = KineticSkill()
        kinetic.bind(
            self.settings.kinetic,
            KineticEngine(
                remotion_project_path=self.settings.kinetic.remotion_project_path,
                output_dir=self.settings.kinetic.output_dir,
            ),
        )

        # 8. Transaction (Optional)
        transaction = None
        if self.settings.crypto.enabled:
            bundle = {
                "solana_provider": SolanaProvider(
                    private_key_base58=get_raw_key(
                        self.settings.crypto.solana_private_key
                    ),
                    rpc_url=str(self.settings.crypto.solana_rpc_url),
                    usdc_mint=self.settings.crypto.solana_usdc_mint,
                ),
                "evm_provider": EVMProvider(
                    private_key_hex=get_raw_key(self.settings.crypto.evm_private_key),
                    rpc_url=str(self.settings.crypto.evm_rpc_url),
                    usdc_address=self.settings.crypto.evm_usdc_address,
                    chain_id=self.settings.crypto.evm_chain_id,
                    risk_router_address=self.settings.crypto.risk_router_address,
                ),
                "encryption": SecretEncryption(
                    get_raw_key(self.settings.crypto.secret_encryption_key)
                ),
                "converter": PriceConverter(),
            }
            # Set 'provider' for backward compatibility (Solana as default)
            bundle["provider"] = bundle["solana_provider"]

            transaction = TransactionSkill()
            transaction.bind(self.settings.crypto, bundle)

        # 9. GoldRush (The Foraging Organ)
        blockchain_data = GoldRushSkill()
        blockchain_data.bind(self.settings.blockchain_data, {"registry": self.registry})

        # 10. Attestation (registered only when a key is present)
        attestation = build_attestation(
            get_raw_key(self.settings.attestation.private_key),
            self.settings.attestation,
        )

        # Register all in the SkillRegistry
        self.registry.register("persistence", persistence)
        self.registry.register("pulse", pulse)
        self.registry.register("reasoning", reasoning)
        self.registry.register("telemetry", telemetry)
        self.registry.register("guard", guard)
        self.registry.register("perception", perception)
        self.registry.register("discovery", discovery)
        self.registry.register("kinetic", kinetic)
        self.registry.register("blockchain_data", blockchain_data)
        if transaction:
            self.registry.register("transaction", transaction)
        if attestation:
            self.registry.register("attestation", attestation)

        # Inject fully-populated registry into skills that cross-call peers
        guard.inject_registry(self.registry)
        blockchain_data.inject_registry(self.registry)

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
