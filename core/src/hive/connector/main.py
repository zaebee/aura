import time
import uuid
from typing import Any

import structlog
from aura.negotiation.v1 import negotiation_pb2
from aura_core import (
    BaseConnector,
    SkillRegistry,
    get_action_name,
)
from aura_core.gen.aura.dna.v1 import (
    Context,
    NegotiationObservation,
    Observation,
    OfferAccepted,
    OfferCountered,
    OfferRejected,
)
from aura_core.gen.aura.dna.v1 import (
    CryptoPaymentInstructions as DNACryptoPayment,
)
from aura_core.gen.aura.dna.v1 import (
    Intent as IntentAction,
)

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
        self, action: IntentAction, context: Context
    ) -> Observation:
        """
        Handle legacy IntentActions that do not have steps.
        This executes the decision and produces an observation (the gRPC response).
        """
        logger.debug("connector_act_started", action=action.action)

        hive = context.hive
        # 1. Map IntentAction to Protobuf NegotiateResponse
        response = negotiation_pb2.NegotiateResponse()
        response.session_token = "sess_" + (hive.request_id or str(uuid.uuid4()))
        response.valid_until_timestamp = int(time.time() + 600)

        # Handle both string and ActionType enum
        action_name = get_action_name(action.action)

        if action_name == "accept":
            response.accepted.final_price = action.negotiation.price
            response.accepted.reservation_code = f"HIVE-{uuid.uuid4()}"

            if self.settings and self.settings.crypto.enabled and self.market_service:
                await self._handle_crypto_lock(response, action, context)

        elif action_name == "counter":
            response.countered.proposed_price = action.negotiation.price
            response.countered.human_message = action.negotiation.message
            response.countered.reason_code = "NEGOTIATION_ONGOING"

        elif action_name == "reject":
            response.rejected.reason_code = "OFFER_TOO_LOW"

        elif action_name == "ui_required":
            response.rejected.reason_code = "UI_REQUIRED"

        else:
            logger.error("unknown_action_type", action=action_name)
            response.rejected.reason_code = "INTERNAL_ERROR"

        # 2. Map to DNA Observation (Binary Bloodstream)
        dna_neg = NegotiationObservation(
            session_token=response.session_token,
            valid_until_timestamp=response.valid_until_timestamp,
        )

        if action_name == "accept":
            dna_neg.accepted = OfferAccepted(
                final_price=response.accepted.final_price,
                reservation_code=response.accepted.reservation_code,
            )
            if response.accepted.HasField("crypto_payment"):
                cp = response.accepted.crypto_payment
                dna_neg.accepted.crypto_payment = DNACryptoPayment(
                    deal_id=cp.deal_id,
                    wallet_address=cp.wallet_address,
                    price=cp.amount,
                    currency=cp.currency,
                    memo=cp.memo,
                    network=cp.network,
                    expires_at=cp.expires_at,
                )
        elif action_name == "counter":
            dna_neg.countered = OfferCountered(
                proposed_price=response.countered.proposed_price,
                reason_code=response.countered.reason_code,
                human_message=response.countered.human_message,
            )
        elif action_name == "reject":
            dna_neg.rejected = OfferRejected(reason_code=response.rejected.reason_code)

        return Observation(
            success=True,
            negotiation=dna_neg,
            event_type=f"negotiation_{action_name}",
            metadata={
                "decision": action_name,
                "item_id": hive.identifier,
                "agent_did": hive.offer.agent_did,
            },
        )

    async def _handle_crypto_lock(
        self,
        response: negotiation_pb2.NegotiateResponse,
        action: IntentAction,
        context: Context,
    ) -> None:
        """Encrypts the reservation code and creates a locked deal via Skills/MarketService."""
        try:
            hive = context.hive
            item_name = hive.item.name or "Aura Item"

            # Use Transaction Skill for price conversion
            obs = await self.registry.execute(
                "transaction",
                "convert_price",
                {
                    "usd_amount": action.negotiation.price,
                    "currency": self.settings.crypto.currency,
                },
            )

            if not obs.success:
                raise ValueError(f"Price conversion failed: {obs.error}")

            crypto_amount = float(obs.metadata.get("crypto_amount", 0.0))

            # MarketService still orchestrates complex multi-protein operations
            # but it is passed to the connector.
            payment_instructions = await self.market_service.create_offer(
                item_id=hive.identifier,
                item_name=item_name,
                secret=response.accepted.reservation_code,
                price=crypto_amount,
                currency=self.settings.crypto.currency,
                buyer_did=hive.offer.agent_did,
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
