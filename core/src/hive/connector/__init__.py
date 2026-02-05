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
    """C - Connector: Maps internal IntentAction to gRPC responses and external systems."""

    def __init__(self, registry: SkillRegistry, market_service: Any = None) -> None:
        super().__init__(registry)
        self.market_service = market_service
        self.settings = get_settings()

    async def _handle_legacy(
        self, action: IntentAction, context: HiveContext
    ) -> Observation:
        """
        Handle legacy IntentActions that do not have steps.
        This executes the decision and produces an observation (the gRPC response).
        """
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
        """Encrypts the reservation code and creates a locked deal via Skills/MarketService."""
        try:
            item_name = context.item_data.get("name", "Aura Item")

            # Use Crypto Skill for price conversion
            obs = await self.registry.execute(
                "crypto",
                "convert_price",
                {"usd_amount": action.price, "currency": self.settings.crypto.currency},
            )

            if not obs.success:
                raise ValueError(f"Price conversion failed: {obs.error}")

            crypto_amount = obs.data

            # MarketService still orchestrates complex multi-protein operations
            # but it is passed to the connector.
            payment_instructions = await self.market_service.create_offer(
                item_id=context.item_id,
                item_name=item_name,
                secret=response.accepted.reservation_code,
                price=crypto_amount,
                currency=self.settings.crypto.currency,
                buyer_did=context.offer.agent_did,
                ttl_seconds=self.settings.crypto.deal_ttl_seconds,
            )

            response.accepted.ClearField("reservation_code")
            response.accepted.crypto_payment.CopyFrom(payment_instructions)

            logger.info(
                "crypto_offer_created",
                deal_id=payment_instructions.deal_id,
                amount=crypto_amount,
                currency=self.settings.crypto.currency,
            )

        except ValueError as e:
            logger.warning("crypto_lock_failed", error=str(e), exc_info=True)
