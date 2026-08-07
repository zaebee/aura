"""WalletRepository — sanctified-wallet persistence, split out of PersistenceSkill.

Tracks which wallets have been "sanctified" for a given asset domain. Methods
are synchronous; callers wrap them in ``asyncio.to_thread`` exactly as the
inline closures did before.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from .engine import SanctifiedWallet


class WalletRepository:
    """Sanctified-wallet lookups over a session factory (`_get_session`)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session = session_factory

    def sanctify(self, wallet_address: str, asset_domain: str) -> None:
        with self._session() as session:
            existing = (
                session.query(SanctifiedWallet)
                .filter_by(wallet_address=wallet_address)
                .first()
            )
            if not existing:
                session.add(
                    SanctifiedWallet(
                        wallet_address=wallet_address,
                        asset_domain=asset_domain,
                    )
                )
            session.commit()

    def is_sanctified(self, wallet_address: str | None) -> bool:
        with self._session() as session:
            return (
                session.query(SanctifiedWallet)
                .filter_by(wallet_address=wallet_address)
                .first()
                is not None
            )
