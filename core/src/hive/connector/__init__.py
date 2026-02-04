import asyncio
import time
import uuid
from typing import Any

import structlog
from aura_core import (
    BaseConnector,
    HiveContext,
    IntentAction,
    Observation,
    SkillRegistry,
)
from config import get_settings
from hive.proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


class HiveConnector(BaseConnector):
    """C - Connector: Maps internal IntentAction to gRPC responses via SkillRegistry."""

    def __init__(self, registry: SkillRegistry, market_service: Any = None) -> None:
        super().__init__(registry)
        self.market_service = market_service
        self.settings = get_settings()

    async def _handle_legacy(
        self, action: IntentAction, context: HiveContext
    ) -> Observation:
        logger.debug("connector_act_started", action=action.action)

        # 1. Map IntentAction to Protobuf NegotiateResponse
        response = negotiation_pb2.NegotiateResponse()
        response.session_token = "sess_" + (context.request_id or str(uuid.uuid4()))
        response.valid_until_timestamp = int(time.time() + 600)

        if action.action == "accept":
            response.accepted.final_price = action.price
            response.accepted.reservation_code = f"HIVE-{uuid.uuid4()}"

            if self.settings.crypto.enabled and self.market_service:
                await self._handle_crypto_lock(response, action, context)

        elif action.action == "counter":
            response.countered.proposed_price = action.price
            response.countered.human_message = action.message
            response.countered.reason_code = "NEGOTIATION_ONGOING"

        elif action.action == "reject":
            response.rejected.reason_code = "OFFER_TOO_LOW"

        elif action.action == "ui_required":
            response.rejected.reason_code = "UI_REQUIRED"

        else:
            logger.error("unknown_action_type", action=action.action)
            response.rejected.reason_code = "INTERNAL_ERROR"

        return Observation(
            success=True,
            data=response,
            event_type=f"negotiation_{action.action}",
            metadata={"decision": action},
        )

    async def _handle_crypto_lock(
        self,
        response: negotiation_pb2.NegotiateResponse,
        action: IntentAction,
        context: HiveContext,
    ) -> None:
        """Encrypts the reservation code and creates a locked deal via Crypto Protein."""
        try:
            item_name = context.item_data.get("name", "Aura Item")

            # NOTE: We should ideally have a 'convert_price' capability in CryptoSkill
            # For now, we'll assume the MarketService handles the details,
            # or we call a skill if we want to be strictly pure.
            # The MarketService itself uses Proteins.

            payment_instructions = await self.market_service.create_offer(
                item_id=context.item_id,
                item_name=item_name,
                secret=response.accepted.reservation_code,
                price=action.price, # MarketService will handle conversion via its internal logic
                currency=self.settings.crypto.currency,
                buyer_did=context.offer.agent_did,
                ttl_seconds=self.settings.crypto.deal_ttl_seconds,
            )

            response.accepted.ClearField("reservation_code")
            response.accepted.crypto_payment.CopyFrom(payment_instructions)

            logger.info(
                "crypto_offer_created",
                deal_id=payment_instructions.deal_id,
                currency=self.settings.crypto.currency,
            )

        except Exception as e:
            logger.error("crypto_lock_failed", error=str(e), exc_info=True)
