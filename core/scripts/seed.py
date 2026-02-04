import asyncio

from hive.aggregator import generate_embedding
from hive.metabolism.logging_config import configure_logging, get_logger
from hive.proteins.storage import StorageProtein

# Configure structured logging on startup
configure_logging()
logger = get_logger("seed")


async def seed() -> None:
    storage = StorageProtein()
    await storage.execute("init_db", {})

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
        vector = generate_embedding(str(raw["desc"]))

        # Upsert via Storage Protein
        obs = await storage.execute(
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
