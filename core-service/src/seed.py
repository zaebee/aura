from db import InventoryItem, SessionLocal
from embeddings import generate_embedding


def seed():
    session = SessionLocal()

    # Список отелей для добавления
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

    print("🌱 Starting Smart Seeding...")

    for raw in raw_items:
        # Проверяем, есть ли уже этот отель
        existing = session.query(InventoryItem).filter_by(id=raw["id"]).first()

        # Генерируем вектор
        print(f"   🧠 Generating embedding for {raw['id']}...")
        vector = generate_embedding(raw["desc"])

        if existing:
            print(f"   🔄 Updating existing item {raw['id']}")
            existing.embedding = vector  # type: ignore
        else:
            print(f"   ✨ Creating new item {raw['id']}")
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
    print("✅ Seeding complete! Database is now semantic-ready.")
    session.close()


if __name__ == "__main__":
    seed()
