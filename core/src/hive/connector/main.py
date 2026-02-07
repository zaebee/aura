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
from aura_core.gen.aura.dna.v1 import (
    ActionType,
    NegotiationObservation,
    OfferAccepted,
    OfferCountered,
    OfferRejected,
)

from hive.proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


class HiveConnector(BaseConnector):
    """C - Connector: Maps internal IntentAction to gRPC responses and external systems."""

    def __init__(
        self, registry: SkillRegistry, market_service: Any = None, settings: Any = None
    ) -> None:
        super().__init__(registry)
        self.market_service = market_service
        self.settings = settings

    async def _handle_legacy(
        self, action: IntentAction, context: HiveContext
    ) -> Observation:
        """
        Handle legacy IntentActions that do not have steps.
        This executes the decision and produces an observation (the betterproto NegotiationObservation).
        """
        logger.debug("connector_act_started", action=action.action)

        # 1. Map IntentAction to betterproto NegotiationObservation
        negotiation_obs = NegotiationObservation()
        negotiation_obs.session_token = "sess_" + (context.request_id or str(uuid.uuid4()))
        negotiation_obs.valid_until_timestamp = int(time.time() + 600)

        # Handle both string and ActionType enum
        action_val = action.action
        if isinstance(action_val, ActionType):
            raw_name = ActionType(action_val).name
            action_name = raw_name.lower().replace("action_type_", "") if raw_name else "unspecified"
        else:
            action_name = str(action_val).lower() if action_val else "unknown"

        if action_name == "accept":
            negotiation_obs.accepted = OfferAccepted(
                final_price=action.price,
                reservation_code=f"HIVE-{uuid.uuid4()}"
            )
            # Crypto lock handling might need update if it was relying on gRPC response
            # For now keeping it simple as it's a legacy handler

        elif action_name == "counter":
            negotiation_obs.countered = OfferCountered(
                proposed_price=action.price,
                human_message=action.message,
                reason_code="NEGOTIATION_ONGOING"
            )

        elif action_name == "reject":
            negotiation_obs.rejected = OfferRejected(reason_code="OFFER_TOO_LOW")

        elif action_name == "ui_required":
            negotiation_obs.rejected = OfferRejected(reason_code="UI_REQUIRED")

        else:
            logger.error("unknown_action_type", action=action_name)
            negotiation_obs.rejected = OfferRejected(reason_code="INTERNAL_ERROR")

        return Observation(
            success=True,
            negotiation=negotiation_obs,
            event_type=f"negotiation_{action_name}",
            metadata={
                "price": str(action.price),
                "item_id": context.item_id,
                "agent_did": context.offer.agent_did,
            },
        )

    async def _handle_crypto_lock(
        self,
        response: negotiation_pb2.NegotiateResponse,
        action: IntentAction,
        context: HiveContext,
    ) -> None:
        """Encrypts the reservation code and creates a locked deal via Skills/MarketService."""
        try:
            item_name = context.item.name or "Aura Item"

            # Use Transaction Skill for price conversion
            obs = await self.registry.execute(
                "transaction",
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
