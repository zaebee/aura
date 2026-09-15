"""EVM trading intents: transfer, EIP-712 signing, router submission."""

from typing import Any

import structlog
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import Observation

from ..engine import EVMProvider
from ..schema import TradeIntentParams

logger = structlog.get_logger(__name__)


class EVMHandlers:
    """EVM domain. Owns only the EVM provider."""

    INTENTS: tuple[str, ...] = ("transfer", "sign_trade_intent", "submit_to_router")

    def __init__(self, evm_provider: EVMProvider | None) -> None:
        self.evm_provider = evm_provider
        self.capabilities = {
            "transfer": self._transfer,
            "sign_trade_intent": self._sign_trade_intent,
            "submit_to_router": self._submit_to_router,
        }

    async def _transfer(self, params: dict[str, Any]) -> Observation:
        network = params.get("network", "base-sepolia")
        amount = float(params["amount"])
        recipient = params["recipient"]

        try:
            if network in ["base-sepolia", "evm"]:
                if not self.evm_provider:
                    return Observation(
                        success=False, error="evm_provider_not_initialized"
                    )
                tx_hash = await self.evm_provider.transfer_usdc(recipient, amount)
                return Observation(
                    success=True,
                    metadata=make_struct({"transaction_hash": tx_hash}),
                )
            else:
                return Observation(
                    success=False, error=f"Transfer not implemented for {network}"
                )
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return Observation(success=False, error=str(e))

    async def _sign_trade_intent(self, params: dict[str, Any]) -> Observation:
        if not self.evm_provider:
            return Observation(success=False, error="evm_provider_not_initialized")

        trade_intent_dict = params.get("intent")
        if not trade_intent_dict:
            return Observation(success=False, error="intent_params_missing")

        try:
            # Validate input using Pydantic schema
            p = TradeIntentParams(**trade_intent_dict)
            result = await self.evm_provider.sign_eip712_trade_intent(p.model_dump())
            return Observation(
                success=True,
                metadata=make_struct(result),
            )
        except Exception as e:
            logger.error(f"EIP-712 signing failed: {e}")
            return Observation(success=False, error=str(e))

    async def _submit_to_router(self, params: dict[str, Any]) -> Observation:
        # Stub for March 9th release
        return Observation(
            success=False,
            error="submit_to_router_not_implemented_pending_abi",
        )
