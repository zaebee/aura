import asyncio
from typing import Any

import structlog
from aura_core import SkillRegistry

from .aggregator import HiveAggregator
from .connector import HiveConnector
from .generator import HiveGenerator
from .membrane import HiveMembrane
from .metabolism import MetabolicLoop
from .services.market import MarketService
from .transformer import AuraTransformer

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
        persistence = registry.get("persistence")
        transaction = registry.get("transaction")
        if transaction and persistence:
            market_service = MarketService(persistence=persistence, transaction=transaction)

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
        self.tasks: list[asyncio.Task[Any]] = []

    async def run_synapse(self, synapse_main: Any) -> asyncio.Task[Any]:
        """
        Starts a synapse as a background task.
        """
        logger.info("starting_synapse_background")
        task = asyncio.create_task(synapse_main())
        self.tasks.append(task)
        return task

    async def stop(self) -> None:
        """
        Gracefully stop all components.
        """
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
