import asyncio
import structlog
from typing import Any
from aura_core import SkillRegistry
from .metabolism import MetabolicLoop
from .aggregator import HiveAggregator
from .transformer import AuraTransformer
from .connector import HiveConnector
from .generator import HiveGenerator
from .membrane import HiveMembrane

logger = structlog.get_logger(__name__)

class HiveCortex:
    """
    Centralized 'Cellular Assembly Unit' responsible for wiring
    all Proteins and Nucleotides.
    """

    @staticmethod
    def build_organism(registry: SkillRegistry, settings: Any) -> MetabolicLoop:
        """
        Standardized method to assemble a full ATCG organism.
        """
        logger.info("building_organism_cortex")

        aggregator = HiveAggregator(registry=registry, settings=settings)
        transformer = AuraTransformer(registry=registry, settings=settings)

        # Market service might need to be injected or built here
        # For simplicity in this refactor, we assume it's handled externally or we build a stub
        market_service = None
        if registry.get("transaction") and registry.get("persistence"):
             from .services.market import MarketService
             market_service = MarketService(
                 persistence=registry.get("persistence"),
                 transaction=registry.get("transaction")
             )

        connector = HiveConnector(
            registry=registry,
            market_service=market_service,
            settings=settings
        )
        generator = HiveGenerator(registry=registry)
        membrane = HiveMembrane(registry=registry)

        return MetabolicLoop(
            aggregator=aggregator,
            transformer=transformer,
            connector=connector,
            generator=generator,
            membrane=membrane,
            registry=registry,
        )

class HiveCell:
    """
    Orchestration unit for running synapses and core metabolism.
    """

    def __init__(self, organism: MetabolicLoop):
        self.organism = organism
        self.tasks = []

    async def run_synapse(self, synapse_main: Any):
        """
        Starts a synapse as a background task.
        """
        logger.info("starting_synapse_background")
        task = asyncio.create_task(synapse_main())
        self.tasks.append(task)
        return task

    async def stop(self):
        """
        Gracefully stop all components.
        """
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
