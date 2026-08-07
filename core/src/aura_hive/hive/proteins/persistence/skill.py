import asyncio
from datetime import datetime
from typing import Any, cast

import redis.asyncio as redis
import structlog
from aura_core import SkillProtocol, make_struct
from aura_core_gen.aura.assets.v1 import Asset
from aura_core_gen.aura.core.v1 import Observation
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from aura_hive.config.database import DatabaseSettings

from .deals import DealRepository
from .engine import (
    Base,
    InventoryItem,
    MetabolicCost,
    RedisCache,
)
from .items import ItemRepository
from .wallet import WalletRepository

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
            "append_negotiation_turn": self._append_negotiation_turn,
            "get_negotiation_history": self._get_negotiation_history,
            "confirm_ground_state": self._confirm_ground_state,
            "get_deal_by_memo": self._get_deal_by_memo_handler,
            "get_deal_by_id": self._get_deal_by_id_handler,
            "update_deal_status": self._update_deal_status,
            "vector_search": self._vector_search,
            "list_items_semantic_search": self._vector_search,
            "get_first_item": self._get_first_item,
            "upsert_item": self._upsert_item,
            "sanctify_wallet": self._sanctify_wallet,
            "is_wallet_sanctified": self._is_wallet_sanctified,
            "log_metabolic_cost": self._log_metabolic_cost,
        }

        # Entity SQL lives in dedicated repositories; the _get_session reference
        # is bound lazily and only invoked at operation time (after bind()).
        self._deals = DealRepository(self._get_session)
        self._items = ItemRepository(self._get_session)
        self._wallets = WalletRepository(self._get_session)

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
        result = await asyncio.to_thread(self._items.get_by_id, item_id)
        if result:
            return Observation(success=True, metadata=make_struct(result))
        return Observation(success=False, error="item_not_found")

    async def _get_first_item(self, params: dict[str, Any]) -> Observation:
        result = await asyncio.to_thread(self._items.get_first)
        if result:
            return Observation(success=True, metadata=make_struct(result))
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

    async def _append_negotiation_turn(self, params: dict[str, Any]) -> Observation:
        if not self.cache:
            return Observation(success=False, error="cache_not_initialized")
        agent_did = str(params.get("agent_did", ""))
        item_id = str(params.get("item_id", ""))
        turn = params.get("turn")
        if not agent_did or not item_id or not isinstance(turn, dict):
            return Observation(
                success=False, error="agent_did, item_id and turn are required"
            )
        try:
            await self.cache.append_negotiation_turn(
                agent_did, item_id, turn, ttl=int(params.get("ttl", 3600))
            )
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _get_negotiation_history(self, params: dict[str, Any]) -> Observation:
        if not self.cache:
            return Observation(success=False, error="cache_not_initialized")
        agent_did = str(params.get("agent_did", ""))
        item_id = str(params.get("item_id", ""))
        if not agent_did or not item_id:
            return Observation(
                success=False, error="agent_did and item_id are required"
            )
        try:
            history = await self.cache.get_negotiation_history(agent_did, item_id)
            return Observation(success=True, metadata=make_struct({"history": history}))
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
            if "secret_content" in deal_data and isinstance(
                deal_data["secret_content"], str
            ):
                deal_data["secret_content"] = bytes.fromhex(deal_data["secret_content"])

            if "expires_at" in deal_data and isinstance(deal_data["expires_at"], str):
                deal_data["expires_at"] = datetime.fromisoformat(
                    deal_data["expires_at"]
                )

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
            await asyncio.to_thread(self._deals.create, params)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _get_deal_by_id_handler(self, params: dict[str, Any]) -> Observation:
        deal_id = params.get("deal_id")
        if not deal_id:
            return Observation(success=False, error="deal_id_required")
        result = await asyncio.to_thread(self._deals.get_by_id, deal_id)
        if result:
            return Observation(success=True, metadata=make_struct(result))
        return Observation(success=False, error="deal_not_found")

    async def _get_deal_by_memo_handler(self, params: dict[str, Any]) -> Observation:
        memo = params.get("memo")
        if not memo:
            return Observation(success=False, error="memo_required")
        result = await asyncio.to_thread(self._deals.get_by_memo, memo)
        if result:
            return Observation(success=True, metadata=make_struct(result))
        return Observation(success=False, error="deal_not_found")

    async def _update_deal_status(self, params: dict[str, Any]) -> Observation:
        deal_id = params.get("deal_id")
        status = params.get("status")
        if not deal_id or not status:
            return Observation(success=False, error="deal_id_and_status_required")
        try:
            success = await asyncio.to_thread(
                self._deals.update_status, deal_id, status, params
            )
            return Observation(success=success)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _upsert_item(self, params: dict[str, Any]) -> Observation:
        """Upsert an item from a native Asset (falls back to legacy dict upsert)."""
        asset = params.get("asset")
        if not asset or not isinstance(asset, Asset):
            return await self._legacy_upsert_item(params)
        try:
            await asyncio.to_thread(self._items.upsert_asset, asset)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _legacy_upsert_item(self, params: dict[str, Any]) -> Observation:
        try:
            await asyncio.to_thread(self._items.upsert_legacy, params)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _sanctify_wallet(self, params: dict[str, Any]) -> Observation:
        wallet_address = params.get("wallet_address")
        if not wallet_address:
            return Observation(success=False, error="wallet_address_required")
        asset_domain = params.get("asset_domain", "")
        await asyncio.to_thread(self._wallets.sanctify, wallet_address, asset_domain)
        return Observation(success=True)

    async def _is_wallet_sanctified(self, params: dict[str, Any]) -> Observation:
        wallet_address = params.get("wallet_address")
        sanctified = await asyncio.to_thread(
            self._wallets.is_sanctified, wallet_address
        )
        return Observation(
            success=True,
            metadata=make_struct({"sanctified": sanctified}),
        )

    async def _log_metabolic_cost(self, params: dict[str, Any]) -> Observation:
        try:

            def log() -> None:
                with self._get_session() as session:
                    cost = MetabolicCost(
                        amount=params["amount"],
                        currency=params["currency"],
                        network=params["network"],
                        endpoint=params["endpoint"],
                        transaction_hash=params.get("tx_hash"),
                    )
                    session.add(cost)
                    session.commit()

            await asyncio.to_thread(log)
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _vector_search(self, params: dict[str, Any]) -> Observation:
        results = await asyncio.to_thread(
            self._items.search_by_vector,
            params.get("query_vector"),
            params.get("limit", 5),
            params.get("min_similarity"),
        )
        return Observation(success=True, metadata=make_struct({"results": results}))
