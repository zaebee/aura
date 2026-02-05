import asyncio

from hive.metabolism.logging_config import configure_logging, get_logger
from hive.proteins.persistence import PersistenceSkill
from hive.proteins.reasoning.enzymes.reasoning_engine import (
    generate_embedding,
    get_embedding_model,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings

# Configure structured logging on startup
configure_logging()
logger = get_logger("seed")


async def seed() -> None:
    # Initialize database persistence
    engine = create_engine(str(settings.database.url))
    SessionLocal = sessionmaker(bind=engine)
    persistence = PersistenceSkill()
    persistence.bind(settings.database, (SessionLocal, engine))

    # Initialize database tables
    await persistence.execute("init_db", {})
    logger.info("database_initialized")

    # Initialize embedding model
    api_key = settings.llm.api_key.get_secret_value()
    embedding_model = get_embedding_model(api_key)
    logger.info("embedding_model_initialized", model="mistral-embed")

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
        vector = generate_embedding(str(raw["desc"]), embedding_model)

        # Upsert via Persistence Skill
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
