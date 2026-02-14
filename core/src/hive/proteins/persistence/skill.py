import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as redis
import structlog
from aura_core import SkillProtocol
from aura_core_gen.aura.assets.v1 import Asset, AssetDomain
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import Observation
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from config.database import DatabaseSettings

from .engine import (
    Base,
    DealStatus,
    InventoryItem,
    LockedDeal,
    RedisCache,
)
from .schema import DealSchema, ItemSchema

logger = structlog.get_logger(__name__)


class PersistenceSkill(
    SkillProtocol[
        DatabaseSettings,
        tuple[sessionmaker, Engine, redis.Redis],
        dict[str, Any],
        Observation,
    ]
):
    """
    Persistence Protein: Handles all database operations.
    Transitioning to Enzymatic Dispatcher for domain-specific asset storage.
    """

    def __init__(self) -> None:
        self.settings: DatabaseSettings | None = None
        self.provider: sessionmaker | None = None
        self.engine: Engine | None = None
        self.redis: redis.Redis | None = None
        self.cache: RedisCache | None = None
        self._capabilities = {
            "init_db": self._init_db,
            "read_item": self._read_item_handler,
            "create_deal": self._create_deal,
            "set_excited_state": self._set_excited_state,
            "confirm_ground_state": self._confirm_ground_state,
            "get_deal_by_memo": self._get_deal_by_memo_handler,
            "get_deal_by_id": self._get_deal_by_id_handler,
            "update_deal_status": self._update_deal_status,
            "vector_search": self._vector_search,
            "list_items_semantic_search": self._vector_search,
            "get_first_item": self._get_first_item,
            "upsert_item": self._upsert_item,
        }

        # Asset Enzymes: Domain-to-method mapping for "Tissue Specificity"
        self._ASSET_ENZYMES: dict[
            int, Callable[[Asset, InventoryItem], None]
        ] = {
            int(AssetDomain.ASSET_DOMAIN_VEHICLE): self._store_vehicle_attributes,
            int(AssetDomain.ASSET_DOMAIN_PROPERTY): self._store_property_attributes,
            int(AssetDomain.ASSET_DOMAIN_EQUIPMENT): self._store_equipment_attributes,
            int(AssetDomain.ASSET_DOMAIN_WORKSPACE): self._store_workspace_attributes,
        }

    def get_name(self) -> str:
        return "persistence"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(
        self,
        settings: DatabaseSettings,
        provider: tuple[sessionmaker, Engine, redis.Redis],
    ) -> None:
        self.settings = settings
        self.provider, self.engine, self.redis = provider
        if self.redis:
            self.cache = RedisCache(self.redis)

    def _get_session(self) -> Session:
        if not self.provider:
            raise RuntimeError("provider_not_initialized")
        return cast(Session, self.provider())

    async def initialize(self) -> bool:
        if not self.settings or not self.provider:
            return False

        if self.redis:
            try:
                await cast(Any, self.redis.ping())
            except Exception as e:
                logger.error("redis_connection_failed", error=e)
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
            logger.error(f"persistence_initialization_failed: {e}")
            return False

    async def post_initialize(self) -> None:
        """Handle database schema creation after successful connection."""
        await self._init_db({})

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Persistence skill error: {e}", exc_info=True)
            return Observation(success=False, error=str(e))

    async def _init_db(self, params: dict[str, Any]) -> Observation:
        if not self.engine:
            return Observation(success=False, error="engine_not_initialized")
        try:

            def create() -> None:
                Base.metadata.create_all(bind=cast(Engine, self.engine))

            await asyncio.to_thread(create)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _read_item_handler(self, params: dict[str, Any]) -> Observation:
        item_id = params.get("item_id")
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
            return Observation(success=True, metadata=protobuf.Struct().from_dict(result))
        return Observation(success=False, error="item_not_found")

    async def _get_first_item(self, params: dict[str, Any]) -> Observation:
        def fetch() -> dict[str, Any] | None:
            with self._get_session() as session:
                item = session.query(InventoryItem).first()
                if item:
                    return ItemSchema.model_validate(item).model_dump()
                return None

        result = await asyncio.to_thread(fetch)
        if result:
            return Observation(success=True, metadata=protobuf.Struct().from_dict(result))
        return Observation(success=False, error="no_items_found")

    async def _set_excited_state(self, params: dict[str, Any]) -> Observation:
        if not self.cache:
            return Observation(success=False, error="cache_not_initialized")
        try:
            deal_id = params.get("id")
            if not deal_id:
                return Observation(success=False, error="id_required")
            await self.cache.set_excited_state(
                str(deal_id), params, ttl=params.get("ttl", 3600)
            )
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _confirm_ground_state(self, params: dict[str, Any]) -> Observation:
        if not self.cache:
            return Observation(success=False, error="cache_not_initialized")
        try:
            deal_id = params.get("deal_id")
            if not deal_id:
                return Observation(success=False, error="deal_id_required")

            deal_data = await self.cache.get_excited_state(str(deal_id))
            if not deal_data:
                # Might already be in ground state
                return Observation(success=True)

            # Move to Postgres
            # Re-map bytes and dates from Redis JSON
            if "secret_content" in deal_data and isinstance(deal_data["secret_content"], str):
                deal_data["secret_content"] = bytes.fromhex(deal_data["secret_content"])

            if "expires_at" in deal_data and isinstance(deal_data["expires_at"], str):
                deal_data["expires_at"] = datetime.fromisoformat(deal_data["expires_at"])

            # Call _create_deal logic (save to Postgres)
            create_obs = await self._create_deal(deal_data)
            if create_obs.success:
                # Update status to PAID if it was confirmed as paid
                if params.get("status") == "PAID":
                    await self._update_deal_status(params)

                await self.cache.delete_excited_state(str(deal_id))
                return Observation(success=True)
            return create_obs
        except Exception as e:
            return Observation(success=False, error=str(e))

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

    async def _get_deal_by_id_handler(self, params: dict[str, Any]) -> Observation:
        deal_id = params.get("deal_id")
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
            return Observation(success=True, metadata=protobuf.Struct().from_dict(result))
        return Observation(success=False, error="deal_not_found")

    async def _get_deal_by_memo_handler(self, params: dict[str, Any]) -> Observation:
        memo = params.get("memo")
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
            return Observation(success=True, metadata=protobuf.Struct().from_dict(result))
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
        """
        Upsert an item using a native Asset object.
        Transitioning from primitive if/else to enzymatic cascades.
        """
        asset = params.get("asset")
        if not asset or not isinstance(asset, Asset):
            # Backward compatibility for legacy dictionary-based upsert
            return await self._legacy_upsert_item(params)

        try:

            def upsert() -> bool:
                with self._get_session() as session:
                    item = session.query(InventoryItem).filter_by(id=asset.identifier).first()
                    if not item:
                        item = InventoryItem(id=asset.identifier)
                        session.add(item)

                    item.name = asset.name
                    if asset.rental_terms:
                        item.base_price = float(asset.rental_terms.base_price)
                        # Assume floor price is 80% if not specified elsewhere
                        item.floor_price = float(asset.rental_terms.base_price) * 0.8

                    # Store common attributes in meta
                    item.meta["description"] = asset.description
                    item.meta["domain"] = asset.domain.name

                    # Enzymatic Cascade: Apply domain-specific attributes
                    domain_val = int(asset.domain)
                    if domain_val in self._ASSET_ENZYMES:
                        enzyme = self._ASSET_ENZYMES[domain_val]
                        enzyme(asset, item)

                    session.commit()
                    return True

            await asyncio.to_thread(upsert)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    def _store_vehicle_attributes(self, asset: Asset, item: InventoryItem) -> None:
        """Enzyme: Specialized storage for Vehicle tissue."""
        # Use hasattr for oneof fields or check field directly if supported by betterproto
        if not asset.vehicle:
            return

        vehicle_data = {
            "brand": str(getattr(asset.vehicle, "brand", "")),
            "model": str(getattr(asset.vehicle, "model", "")),
            "year": int(getattr(asset.vehicle, "year", 0)),
            "vin": str(getattr(asset.vehicle, "vin", "")),
            "color": str(getattr(asset.vehicle, "color", "")),
            "license_plate": str(getattr(asset.vehicle, "license_plate", "")),
        }
        item.meta["vehicle_details"] = vehicle_data

    def _store_property_attributes(self, asset: Asset, item: InventoryItem) -> None:
        """Enzyme: Specialized storage for Property tissue."""
        if not asset.property:
            return
        item.meta["property_details"] = asset.property.to_dict()

    def _store_equipment_attributes(self, asset: Asset, item: InventoryItem) -> None:
        """Enzyme: Specialized storage for Equipment tissue."""
        if not asset.equipment:
            return
        item.meta["equipment_details"] = asset.equipment.to_dict()

    def _store_workspace_attributes(self, asset: Asset, item: InventoryItem) -> None:
        """Enzyme: Specialized storage for Workspace tissue."""
        if not asset.workspace:
            return
        item.meta["workspace_details"] = asset.workspace.to_dict()

    async def _legacy_upsert_item(self, params: dict[str, Any]) -> Observation:
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
        # Struct.from_dict expects a dict with standard JSON types.
        # results is a list of dicts, which should be fine.
        return Observation(success=True, metadata=protobuf.Struct().from_dict({"results": results}))
