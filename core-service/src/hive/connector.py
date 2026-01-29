import asyncio
import time

import structlog
from crypto.pricing import PriceConverter
from hive.dna import Decision, HiveContext, Observation

from config import get_settings
from db import SessionLocal
from proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


class HiveConnector:
    """C - Connector: Maps decisions to gRPC responses and interacts with external systems (Solana)."""

    def __init__(self, market_service=None):
        self.market_service = market_service
        self.settings = get_settings()

    async def act(self, action: Decision, context: HiveContext) -> Observation:
        """
        Execute the decision and produce an observation (the gRPC response).

        Args:
            action: The decision from the Transformer.
            context: The Hive context.
        """
        logger.debug("connector_act_started", action=action.action)

        # 1. Map Decision to Protobuf NegotiateResponse
        response = negotiation_pb2.NegotiateResponse()
        response.session_token = "sess_" + (context.request_id or str(int(time.time())))
        response.valid_until_timestamp = int(time.time() + 600)

        if action.action == "accept":
            response.accepted.final_price = action.price
            # Default reservation code if crypto not used
            response.accepted.reservation_code = f"HIVE-{int(time.time())}"

            # 2. Handle Solana logic if enabled and MarketService is provided
            if self.settings.crypto.enabled and self.market_service:
                await self._handle_crypto_lock(response, action, context)

        elif action.action == "counter":
            response.countered.proposed_price = action.price
            response.countered.human_message = action.message
            response.countered.reason_code = "NEGOTIATION_ONGOING"

        elif action.action == "reject":
            response.rejected.reason_code = "OFFER_TOO_LOW"

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
        action: Decision,
        context: HiveContext,
    ):
        """Encrypts the reservation code and creates a locked deal on Solana."""

        def create_offer_sync():
            with SessionLocal() as session:
                # Use item name from context to avoid redundant query
                item_name = context.item_data.get("name", "Aura Item")

                converter = PriceConverter(
                    use_fixed_rates=self.settings.crypto.use_fixed_rates
                )

                # Convert USD price to crypto amount
                crypto_amount = converter.convert_usd_to_crypto(
                    usd_amount=action.price,
                    crypto_currency=self.settings.crypto.currency,
                )

                # Create the offer via MarketService
                return crypto_amount, self.market_service.create_offer(
                    db=session,
                    item_id=context.item_id,
                    item_name=item_name,
                    secret=response.accepted.reservation_code,
                    price=crypto_amount,
                    currency=self.settings.crypto.currency,
                    buyer_did=context.agent_did,
                    ttl_seconds=self.settings.crypto.deal_ttl_seconds,
                )

        try:
            crypto_amount, payment_instructions = await asyncio.to_thread(
                create_offer_sync
            )

            # Update the response: clear plain reservation_code, set crypto_payment
            response.accepted.ClearField("reservation_code")
            response.accepted.crypto_payment.CopyFrom(payment_instructions)

            logger.info(
                "crypto_offer_created",
                deal_id=payment_instructions.deal_id,
                amount=crypto_amount,
                currency=self.settings.crypto.currency,
            )

        except Exception as e:
            logger.error("crypto_lock_failed", error=str(e), exc_info=True)
            # Fallback: keep the plain reservation_code if crypto fails
            # (or we could decide to fail the whole request)
