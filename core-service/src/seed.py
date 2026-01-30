from src.db import InventoryItem, SessionLocal
from src.embeddings import generate_embedding
from src.logging_config import configure_logging, get_logger

# Configure structured logging on startup
configure_logging()
logger = get_logger("seed")


def seed() -> None:
    session = SessionLocal()

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
        # Check if hotel already exists
        existing = session.query(InventoryItem).filter_by(id=raw["id"]).first()

        # Generate vector embedding
        logger.info("embedding_generation_started", item_id=raw["id"])
        vector = generate_embedding(str(raw["desc"]))

        if existing:
            logger.info("item_updated", item_id=raw["id"])
            existing.embedding = vector  # type: ignore
        else:
            logger.info("item_created", item_id=raw["id"], name=raw["name"])
            item = InventoryItem(
                id=raw["id"],
                name=raw["name"],
                base_price=raw["base"],
                floor_price=raw["floor"],
                meta=raw["meta"],
                embedding=vector,
            )
            session.add(item)

    session.commit()
    logger.info("seeding_completed", status="success")
    session.close()


if __name__ == "__main__":
    seed()
