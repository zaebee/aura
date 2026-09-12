"""ItemRepository — inventory-item persistence, split out of PersistenceSkill.

Read / upsert / vector-search over InventoryItem. Async; the skill awaits
these methods directly. Domain-specific attributes are applied via the tissue
enzymes during asset upsert, keeping tissue specificity out of the skill.
"""

from collections.abc import Callable
from typing import Any, cast

from aura_core_gen.aura.assets.v1 import Asset
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import InventoryItem
from .schema import ItemSchema
from .tissue import ASSET_ENZYMES


class ItemRepository:
    """CRUD + semantic search for InventoryItem over an async session factory."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session = session_factory

    async def get_by_id(self, item_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(select(InventoryItem).filter_by(id=item_id))
            item = result.scalar_one_or_none()
            return ItemSchema.model_validate(item).model_dump() if item else None

    async def get_first(self) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(select(InventoryItem).limit(1))
            item = result.scalars().first()
            return ItemSchema.model_validate(item).model_dump() if item else None

    async def upsert_asset(self, asset: Asset) -> None:
        """Upsert from a native Asset, dispatching tissue-specific attributes."""
        async with self._session() as session:
            result = await session.execute(
                select(InventoryItem).filter_by(id=asset.identifier)
            )
            item = result.scalar_one_or_none()
            if not item:
                item = InventoryItem(id=asset.identifier)
                session.add(item)

            item.name = asset.name
            if asset.rental_terms:
                # base_price is a runtime betterproto field absent from the
                # RentalTerms type stub; cast keeps mypy honest without getattr.
                base_price = float(cast(Any, asset.rental_terms).base_price)
                item.base_price = base_price
                # Assume floor price is 80% if not specified elsewhere.
                item.floor_price = base_price * 0.8

            item.meta["description"] = asset.description
            item.meta["domain"] = asset.domain.name

            # Enzymatic cascade: apply domain-specific (tissue) attributes.
            enzyme = ASSET_ENZYMES.get(int(asset.domain))
            if enzyme:
                enzyme(asset, item)

            await session.commit()

    async def upsert_legacy(self, params: dict[str, Any]) -> None:
        """Backward-compatible dictionary-based upsert."""
        item_id = params.get("id")
        async with self._session() as session:
            result = await session.execute(select(InventoryItem).filter_by(id=item_id))
            item = result.scalar_one_or_none()
            if item:
                item.name = params.get("name", item.name)
                item.base_price = params.get("base_price", item.base_price)
                item.floor_price = params.get("floor_price", item.floor_price)
                item.meta = params.get("meta", item.meta)
                item.embedding = params.get("embedding", item.embedding)
            else:
                item = InventoryItem(
                    id=item_id,
                    name=params["name"],
                    base_price=params["base_price"],
                    floor_price=params["floor_price"],
                    meta=params.get("meta", {}),
                    embedding=params.get("embedding"),
                )
                session.add(item)
            await session.commit()

    async def search_by_vector(
        self, query_vector: Any, limit: int, min_similarity: float | None
    ) -> list[dict[str, Any]]:
        """Cosine-distance semantic search over item embeddings."""
        if query_vector is None:
            return []
        async with self._session() as session:
            result = await session.execute(
                select(
                    InventoryItem,
                    InventoryItem.embedding.cosine_distance(query_vector).label(
                        "distance"
                    ),
                )
                .order_by(InventoryItem.embedding.cosine_distance(query_vector))
                .limit(limit)
            )
            rows = result.all()

            response_items: list[dict[str, Any]] = []
            for item, distance in rows:
                if distance is None:
                    # No embedding on this row: cosine_distance is NULL.
                    # Skipped, never fatal (matches the negotiation-history
                    # rule for malformed entries).
                    continue
                similarity = 1 - distance
                if min_similarity and similarity < min_similarity:
                    continue
                response_items.append(
                    ItemSchema.model_validate(item).model_dump()
                    | {"similarity_score": similarity}
                )
            return response_items
