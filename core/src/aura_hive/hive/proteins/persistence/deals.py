"""DealRepository — locked-deal persistence, split out of PersistenceSkill.

Keeps the deal SQL in one place so the skill's handlers stay thin
(params -> repo -> Observation). Async; the skill awaits these methods
directly.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import DealStatus, LockedDeal
from .schema import DealSchema


class DealRepository:
    """CRUD for LockedDeal rows over an async session factory."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session = session_factory

    async def create(self, params: dict[str, Any]) -> None:
        async with self._session() as session:
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
            await session.commit()

    async def get_by_id(self, deal_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(select(LockedDeal).filter_by(id=deal_id))
            deal = result.scalar_one_or_none()
            return DealSchema.model_validate(deal).model_dump() if deal else None

    async def get_by_memo(self, memo: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.execute(
                select(LockedDeal).filter_by(payment_memo=memo)
            )
            deal = result.scalar_one_or_none()
            return DealSchema.model_validate(deal).model_dump() if deal else None

    async def update_status(
        self, deal_id: str, status: str, params: dict[str, Any]
    ) -> bool:
        async with self._session() as session:
            result = await session.execute(select(LockedDeal).filter_by(id=deal_id))
            deal = result.scalar_one_or_none()
            if not deal:
                return False

            deal.status = DealStatus(status)
            if status == "PAID":
                deal.transaction_hash = params.get("transaction_hash")
                deal.block_number = params.get("block_number")
                deal.from_address = params.get("from_address")
                deal.paid_at = params.get("paid_at", datetime.now(UTC))

            deal.updated_at = datetime.now(UTC)
            await session.commit()
            return True
