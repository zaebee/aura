from typing import TYPE_CHECKING, Any, cast

import dspy
import structlog
from aura_core import SkillProtocol, SkillRegistry, get_raw_key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hive.aggregator import HiveAggregator
from hive.connector import HiveConnector
from hive.generator import HiveGenerator
from hive.membrane import HiveMembrane
from hive.metabolism import MetabolicLoop
from hive.proteins.guard import GuardSkill
from hive.proteins.guard.logic import OutputGuard
from hive.proteins.persistence import PersistenceSkill
from hive.proteins.pulse import PulseSkill

# --- Implementation Details (Flattened) ---
from hive.proteins.pulse.broker import NatsProvider
from hive.proteins.reasoning import ReasoningSkill
from hive.proteins.reasoning.engine import get_embedding_model
from hive.proteins.telemetry import TelemetrySkill
from hive.proteins.transaction import TransactionSkill
from hive.proteins.transaction.solana import (
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

    async def build_organism(self) -> MetabolicLoop:
        """
        Instantiate, bind, and wire all Proteins and Nucleotides.
        Returns a fully functional MetabolicLoop.
        """
        logger.info("assembling_hive_cell")

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
                persistence=persistence,
                transaction=transaction
            )
            self.market_service = market_service
            logger.info("market_service_wired")

        connector = HiveConnector(
            registry=self.registry,
            market_service=market_service,
            settings=self.settings
        )
        generator = HiveGenerator(registry=self.registry)
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

        # 4. Start Synapses (optional background tasks)
        await self._init_synapses()

        logger.info("organism_assembly_complete")
        return self.metabolism

    async def _init_synapses(self) -> None:
        """Initialize and start all configured synapses as background tasks."""
        if not self.settings.synapses.enabled:
            return

        import asyncio
        import importlib.util
        from pathlib import Path

        for synapse_name in self.settings.synapses.active_synapses:
            logger.info("starting_synapse", synapse=synapse_name)

            # Convention: synapses/<name>/main.py
            synapse_path = Path(__file__).resolve().parents[3] / "synapses" / synapse_name / "main.py"
            if not synapse_path.exists():
                logger.error("synapse_main_not_found", synapse=synapse_name, path=str(synapse_path))
                continue

            # Start as a background task
            # In a real system, we'd use a more robust orchestration
            async def run_synapse(name, path):
                try:
                    spec = importlib.util.spec_from_file_location(f"synapse.{name}", path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "main"):
                            await module.main()
                        elif hasattr(module, "run"):
                            await module.run()
                except Exception as e:
                    logger.error("synapse_crashed", synapse=name, error=str(e))

            asyncio.create_task(run_synapse(synapse_name, synapse_path))

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
        guard.bind(self.settings.safety, OutputGuard(safety_settings=self.settings.safety))

        # 6. Transaction (Optional)
        transaction = None
        if self.settings.crypto.enabled:
            bundle = {
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
                    if hasattr(skill, "post_initialize") and callable(skill.post_initialize):
                        await skill.post_initialize()
