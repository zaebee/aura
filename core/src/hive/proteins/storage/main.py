import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast

from aura_core import Observation, SkillProtocol
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from config.database import DatabaseSettings

from ._internal import (
    Base,
    DealStatus,
    InventoryItem,
    LockedDeal,
)
from .schema import DealSchema, ItemSchema

logger = logging.getLogger(__name__)


class StorageSkill(
    SkillProtocol[DatabaseSettings, tuple[sessionmaker, Engine], dict[str, Any], Observation]
):
    """
    Storage Protein: Handles all database operations.
    Standardized following the Crystalline Protein Standard.
    """

    def __init__(self) -> None:
        self.settings: DatabaseSettings | None = None
        self.provider: sessionmaker | None = None
        self.engine: Engine | None = None

    def get_name(self) -> str:
        return "storage"

    def get_capabilities(self) -> list[str]:
        return [
            "read_item",
            "create_deal",
            "get_deal_by_memo",
            "get_deal_by_id",
            "update_deal_status",
            "vector_search",
            "list_items_semantic_search",
            "init_db",
            "upsert_item",
            "get_first_item",
        ]

    def bind(
        self, settings: DatabaseSettings, provider: tuple[sessionmaker, Engine]
    ) -> None:
        self.settings = settings
        self.provider, self.engine = provider

    def _get_session(self) -> Session:
        if not self.provider:
            raise RuntimeError("provider_not_initialized")
        return cast(Session, self.provider())

    async def initialize(self) -> bool:
        if not self.settings or not self.provider:
            return False

        from pgvector.sqlalchemy import Vector
        # DNA Rule: Dynamic configuration of vector dimension
        InventoryItem.__table__.c.embedding.type = Vector(
            self.settings.vector_dimension
        )

        try:

            def check() -> bool:
                with self._get_session() as session:
                    session.execute(text("SELECT 1"))
                return True

            return await asyncio.to_thread(check)
        except Exception as e:
            logger.error(f"storage_initialization_failed: {e}")
            return False

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        if intent == "init_db":
            return await self._init_db()
        elif intent == "read_item":
            return await self._read_item(params.get("item_id"))
        elif intent == "create_deal":
            return await self._create_deal(params)
        elif intent == "get_deal_by_memo":
            return await self._get_deal_by_memo(params.get("memo"))
        elif intent == "get_deal_by_id":
            return await self._get_deal_by_id(params.get("deal_id"))
        elif intent == "update_deal_status":
            return await self._update_deal_status(params)
        elif intent in ["vector_search", "list_items_semantic_search"]:
            return await self._vector_search(params)
        elif intent == "get_first_item":
            return await self._get_first_item()
        elif intent == "upsert_item":
            return await self._upsert_item(params)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def _init_db(self) -> Observation:
        if not self.engine:
            return Observation(success=False, error="engine_not_initialized")
        try:

            def create() -> None:
                Base.metadata.create_all(bind=cast(Engine, self.engine))

            await asyncio.to_thread(create)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _read_item(self, item_id: str | None) -> Observation:
        if not item_id:
            return Observation(success=False, error="item_id_required")

        def fetch() -> dict[str, Any] | None:
            with self._get_session() as session:
                item = session.query(InventoryItem).filter_by(id=item_id).first()
                if item:
                    return ItemSchema.model_validate(item).model_dump()
                return None

        result = await asyncio.to_thread(fetch)
        if result:
            return Observation(success=True, data=result)
        return Observation(success=False, error="item_not_found")

    async def _get_first_item(self) -> Observation:
        def fetch() -> dict[str, Any] | None:
            with self._get_session() as session:
                item = session.query(InventoryItem).first()
                if item:
                    return ItemSchema.model_validate(item).model_dump()
                return None

        result = await asyncio.to_thread(fetch)
        if result:
            return Observation(success=True, data=result)
        return Observation(success=False, error="no_items_found")

    async def _create_deal(self, params: dict[str, Any]) -> Observation:
        try:

            def create() -> bool:
                with self._get_session() as session:
                    deal = LockedDeal(
                        id=params["id"],
                        item_id=params["item_id"],
                        item_name=params["item_name"],
                        final_price=params["final_price"],
                        currency=params["currency"],
                        payment_memo=params["payment_memo"],
                        secret_content=params["secret_content"],
                        status=DealStatus.PENDING,
                        buyer_did=params.get("buyer_did"),
                        expires_at=params["expires_at"],
                    )
                    session.add(deal)
                    session.commit()
                    return True

            await asyncio.to_thread(create)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _get_deal_by_id(self, deal_id: Any) -> Observation:
        if not deal_id:
            return Observation(success=False, error="deal_id_required")

        def fetch() -> dict[str, Any] | None:
            with self._get_session() as session:
                deal = session.query(LockedDeal).filter_by(id=deal_id).first()
                if deal:
                    return DealSchema.model_validate(deal).model_dump()
                return None

        result = await asyncio.to_thread(fetch)
        if result:
            return Observation(success=True, data=result)
        return Observation(success=False, error="deal_not_found")

    async def _get_deal_by_memo(self, memo: str | None) -> Observation:
        if not memo:
            return Observation(success=False, error="memo_required")

        def fetch() -> dict[str, Any] | None:
            with self._get_session() as session:
                deal = session.query(LockedDeal).filter_by(payment_memo=memo).first()
                if deal:
                    return DealSchema.model_validate(deal).model_dump()
                return None

        result = await asyncio.to_thread(fetch)
        if result:
            return Observation(success=True, data=result)
        return Observation(success=False, error="deal_not_found")

    async def _update_deal_status(self, params: dict[str, Any]) -> Observation:
        deal_id = params.get("deal_id")
        status = params.get("status")

        try:

            def update() -> bool:
                with self._get_session() as session:
                    deal = session.query(LockedDeal).filter_by(id=deal_id).first()
                    if not deal:
                        return False

                    deal.status = DealStatus(status)
                    if status == "PAID":
                        deal.transaction_hash = params.get("transaction_hash")
                        deal.block_number = params.get("block_number")
                        deal.from_address = params.get("from_address")
                        deal.paid_at = params.get("paid_at", datetime.now(UTC))

                    deal.updated_at = datetime.now(UTC)
                    session.commit()
                    return True

            success = await asyncio.to_thread(update)
            return Observation(success=success)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _upsert_item(self, params: dict[str, Any]) -> Observation:
        item_id = params.get("id")
        try:

            def upsert() -> bool:
                with self._get_session() as session:
                    item = session.query(InventoryItem).filter_by(id=item_id).first()
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
                    session.commit()
                    return True

            await asyncio.to_thread(upsert)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _vector_search(self, params: dict[str, Any]) -> Observation:
        query_vector = params.get("query_vector")
        limit = params.get("limit", 5)
        min_similarity = params.get("min_similarity")

        def search() -> list[dict[str, Any]]:
            with self._get_session() as session:
                results = (
                    session.query(
                        InventoryItem,
                        InventoryItem.embedding.cosine_distance(query_vector).label(
                            "distance"
                        ),
                    )
                    .order_by(InventoryItem.embedding.cosine_distance(query_vector))
                    .limit(limit)
                    .all()
                )

                response_items = []
                for item, distance in results:
                    similarity = 1 - distance
                    if min_similarity and similarity < min_similarity:
                        continue

                    response_items.append(
                        ItemSchema.model_validate(item).model_dump()
                        | {"similarity_score": similarity}
                    )
                return response_items

        results = await asyncio.to_thread(search)
        return Observation(success=True, data=results)
