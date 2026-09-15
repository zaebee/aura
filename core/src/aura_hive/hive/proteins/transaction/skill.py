from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aura_core import SkillProtocol
from aura_core_gen.aura.core.v1 import Observation

from aura_hive.config.crypto import CryptoSettings
from aura_hive.hive.metabolism import MetabolicSecurityError

from .engine import EVMProvider, PriceConverter, SecretEncryption
from .handlers import (
    EVMHandlers,
    PaymentsHandlers,
    PricingHandlers,
    RWAHandlers,
    SecretsHandlers,
)
from .solana_engine import SolanaProvider

logger = structlog.get_logger(__name__)

# Domain handlers in dispatch order. The facade merges their capability
# maps at bind() time; the union is the skill's public contract.
_HANDLER_CLASSES = (
    PaymentsHandlers,
    SecretsHandlers,
    PricingHandlers,
    EVMHandlers,
    RWAHandlers,
)

# Public contract, available before bind(): every intent exactly once.
_CAPABILITY_ORDER: tuple[str, ...] = tuple(
    intent for handler_cls in _HANDLER_CLASSES for intent in handler_cls.capabilities
)


class TransactionSkill(
    SkillProtocol[CryptoSettings, dict[str, Any], dict[str, Any], Observation]
):
    """
    Transaction Protein: thin facade over five domain handlers.

    Owns lifecycle (bind/initialize/close) and fail-closed dispatch.
    Every intent lives in exactly one handler; see handlers/.
    """

    def __init__(self) -> None:
        self.settings: CryptoSettings | None = None
        self.provider: SolanaProvider | None = None
        self.solana_provider: SolanaProvider | None = None
        self.evm_provider: EVMProvider | None = None
        self.encryption: SecretEncryption | None = None
        self.converter: PriceConverter | None = None
        self._capabilities: dict[
            str, Callable[[dict[str, Any]], Awaitable[Observation]]
        ] = {}

    def get_name(self) -> str:
        return "transaction"

    def get_capabilities(self) -> list[str]:
        if self._capabilities:
            return list(self._capabilities.keys())
        return list(_CAPABILITY_ORDER)

    def bind(self, settings: CryptoSettings, provider: dict[str, Any]) -> None:
        self.settings = settings
        self.provider = provider.get("provider")
        self.solana_provider = provider.get("solana_provider")
        self.evm_provider = provider.get("evm_provider")
        self.encryption = provider.get("encryption")
        self.converter = provider.get("converter")

        handlers = (
            PaymentsHandlers(provider=self.provider, settings=self.settings),
            SecretsHandlers(encryption=self.encryption),
            PricingHandlers(converter=self.converter, settings=self.settings),
            EVMHandlers(evm_provider=self.evm_provider),
            RWAHandlers(solana_provider=self.solana_provider, settings=self.settings),
        )
        self._capabilities = {}
        for handler in handlers:
            for intent, method_name in handler.capabilities.items():
                self._capabilities[intent] = getattr(handler, method_name)

    async def initialize(self) -> bool:
        if self.settings and self.settings.wallet_address and self.provider:
            derived_addr = str(self.provider.keypair.pubkey())
            if derived_addr != self.settings.wallet_address:
                logger.error(
                    "wallet_address_mismatch",
                    expected=self.settings.wallet_address,
                    derived=derived_addr,
                )
                return False
        return True

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if (
            not self.provider
            or not self.encryption
            or not self.converter
            or not self.settings
        ):
            return Observation(success=False, error="transaction_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except MetabolicSecurityError:
            raise
        except Exception as e:
            logger.error(f"Transaction skill error: {e}")
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
