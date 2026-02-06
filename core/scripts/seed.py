import asyncio

import dspy
from aura_core import get_raw_key
from hive.metabolism.logging_config import configure_logging, get_logger
from hive.proteins.persistence.main import PersistenceSkill
from hive.proteins.reasoning.enzymes.reasoning_engine import get_embedding_model
from hive.proteins.reasoning.main import ReasoningSkill
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings

# Configure structured logging on startup
configure_logging()
logger = get_logger("seed")


async def seed() -> None:
    # --- Provider Factories (Trinity Pattern) ---

    # Persistence Provider
    engine = create_engine(str(settings.database.url))
    SessionLocal = sessionmaker(bind=engine)

    # Reasoning Provider
    lm = None
    embedder = None
    if settings.llm.model.lower() != "rule":
        lm = dspy.LM(settings.llm.model)
        embedder = get_embedding_model(get_raw_key(settings.llm.api_key))
    reasoning_provider = {"lm": lm, "embedder": embedder}

    # --- Skill Instantiation & Binding ---

    persistence = PersistenceSkill()
    persistence.bind(settings.database, (SessionLocal, engine))

    reasoning = ReasoningSkill()
    reasoning.bind(settings.llm, reasoning_provider)

    # Initialize Skills
    if await persistence.initialize():
        await persistence.execute("init_db", {})
        logger.info("db_initialized")
    else:
        logger.error("db_initialization_failed")
        return

    if not await reasoning.initialize():
        logger.error("reasoning_initialization_failed")
        return

    # List of hotels to add
    raw_items = [
        {
            "id": "hotel_alpha",
            "name": "Grand Hotel Alpha (Luxury)",
            "base": 1000.0,
            "floor": 800.0,
            "meta": {"stars": 5, "location": "Dubai"},
            "desc": "Luxury 5-star hotel in Dubai downtown with infinity pool, spa, and ocean view. Best for business and elite travelers.",
        },
        {
            "id": "hostel_beta",
            "name": "Backpacker Hostel Beta",
            "base": 50.0,
            "floor": 40.0,
            "meta": {"stars": 2, "location": "Bali"},
            "desc": "Cheap, cozy hostel in Bali near the beach. Perfect for digital nomads, surfers and students. Shared rooms available.",
        },
    ]

    logger.info("seeding_started", item_count=len(raw_items))

    for raw in raw_items:
        # Generate vector embedding
        logger.info("embedding_generation_started", item_id=raw["id"])
        emb_obs = await reasoning.execute(
            "generate_embedding", {"text": str(raw["desc"])}
        )
        if emb_obs.success:
            vector = emb_obs.data
        else:
            logger.warning(
                "embedding_generation_failed_using_dummy",
                item_id=raw["id"],
                error=emb_obs.error,
            )
            vector = [0.0] * settings.database.vector_dimension

        # Upsert via Persistence Protein
        obs = await persistence.execute(
            "upsert_item",
            {
                "id": raw["id"],
                "name": raw["name"],
                "base_price": raw["base"],
                "floor_price": raw["floor"],
                "meta": raw["meta"],
                "embedding": vector,
            },
        )

        if obs.success:
            logger.info("item_upserted", item_id=raw["id"])
        else:
            logger.error("item_upsert_failed", item_id=raw["id"], error=obs.error)

    logger.info("seeding_completed", status="success")


if __name__ == "__main__":
    asyncio.run(seed())
