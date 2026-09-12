"""WalletRepository — sanctified-wallet persistence, split out of PersistenceSkill.

Tracks which wallets have been "sanctified" for a given asset domain.
Async; the skill awaits these methods directly.
"""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import SanctifiedWallet


class WalletRepository:
    """Sanctified-wallet lookups over an async session factory."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session = session_factory

    async def sanctify(self, wallet_address: str, asset_domain: str) -> None:
        async with self._session() as session:
            result = await session.execute(
                select(SanctifiedWallet).filter_by(wallet_address=wallet_address)
            )
            if result.scalar_one_or_none() is None:
                session.add(
                    SanctifiedWallet(
                        wallet_address=wallet_address,
                        asset_domain=asset_domain,
                    )
                )
            await session.commit()

    async def is_sanctified(self, wallet_address: str | None) -> bool:
        async with self._session() as session:
            result = await session.execute(
                select(SanctifiedWallet).filter_by(wallet_address=wallet_address)
            )
            return result.scalar_one_or_none() is not None
