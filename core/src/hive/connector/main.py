import time
import uuid
from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    BaseConnector,
    SkillRegistry,
)
from aura_core_gen.aura.core.google import protobuf
from aura_core_gen.aura.core.v1 import (
    ActionType,
    Context,
    Intent,
    NegotiationObservation,
    Observation,
    OfferAccepted,
    OfferCountered,
    OfferRejected,
)

logger = structlog.get_logger(__name__)


def _get_metadata_dict(obj: Any) -> dict[str, Any]:
    meta = getattr(obj, "metadata", {})
    if hasattr(meta, "to_dict"):
        return cast(dict[str, Any], meta.to_dict())
    return meta if isinstance(meta, dict) else {}


class HiveConnector(BaseConnector):
    """C - Connector: Maps internal Intent to Observations."""

    def __init__(
        self, registry: SkillRegistry, market_service: Any = None, settings: Any = None
    ) -> None:
        super().__init__(registry)
        self.market_service = market_service
        self.settings = settings

    async def _handle_legacy(self, action: Intent, context: Context) -> Observation:
        """
        Handle Intents that do not have steps.
        This executes the decision and produces an observation.
        """
        logger.debug("connector_act_started", action=action.action)

        neg_obs = NegotiationObservation(
            item_identifier=context.hive.item_identifier
            if context.hive
            else context.identifier,
            valid_until_timestamp=int(time.time() + 600),
        )

        action_type = action.action
        event_type = "negotiation_unknown"

        params_name, params_value = betterproto.which_one_of(action, "params")
        neg_intent = params_value if params_name == "negotiation" else None

        if action_type == ActionType.ACTION_TYPE_ACCEPT:
            event_type = "negotiation_accept"
            reservation_code = f"HIVE-{uuid.uuid4()}"
            price = neg_intent.price if neg_intent else 0.0
            neg_obs.accepted = OfferAccepted(
                final_price=price,
                reservation_code=reservation_code,
            )

            if (
                self.settings
                and hasattr(self.settings, "crypto")
                and self.settings.crypto.enabled
                and self.market_service
            ):
                await self._handle_crypto_lock(neg_obs, action, context)

        elif action_type == ActionType.ACTION_TYPE_COUNTER:
            event_type = "negotiation_counter"
            price = neg_intent.price if neg_intent else 0.0
            message = neg_intent.message if neg_intent else ""
            neg_obs.countered = OfferCountered(
                proposed_price=price,
                human_message=message,
                reason_code="NEGOTIATION_ONGOING",
            )

        elif action_type == ActionType.ACTION_TYPE_REJECT:
            event_type = "negotiation_reject"
            neg_obs.rejected = OfferRejected(
                reason_code="OFFER_TOO_LOW",
            )

        elif action_type == ActionType.ACTION_TYPE_EVALUATE:  # UI Required
            event_type = "negotiation_ui_required"
            neg_obs.rejected = OfferRejected(
                reason_code="UI_REQUIRED",
            )

        else:
            logger.error("unknown_action_type", action=action_type)
            neg_obs.rejected = OfferRejected(reason_code="INTERNAL_ERROR")

        obs_meta = _get_metadata_dict(context)
        obs_meta.update(
            {
                "item_id": str(
                    context.hive.item_identifier if context.hive else context.identifier
                ),
                "agent_did": str(
                    context.hive.offer.agent_did
                    if context.hive and context.hive.offer
                    else "unknown"
                ),
                "payment_uri": str(neg_obs.payment_uri or ""),
            }
        )

        return Observation(
            success=True,
            negotiation=neg_obs,
            event_type=event_type,
            trace=context.trace,
            metadata=protobuf.Struct().from_dict(obs_meta),
        )

    async def _handle_crypto_lock(
        self,
        neg_obs: NegotiationObservation,
        action: Intent,
        context: Context,
    ) -> None:
        """Encrypts the reservation code and creates a locked deal via Skills/MarketService."""
        try:
            item_id = (
                context.hive.item_identifier if context.hive else context.identifier
            )
            item_name = str(context.metadata.to_dict().get("item_name", "Aura Item"))
            params_name, params_value = betterproto.which_one_of(action, "params")
            neg_intent = params_value if params_name == "negotiation" else None
            price = neg_intent.price if neg_intent else 0.0
            agent_did = (
                context.hive.offer.agent_did
                if context.hive and context.hive.offer
                else "unknown"
            )

            # Use Transaction Skill for price conversion
            obs = await self.registry.execute(
                "transaction",
                "convert_price",
                {"usd_amount": price, "currency": self.settings.crypto.currency},
            )

            if not obs.success:
                raise ValueError(f"Price conversion failed: {obs.error}")

            crypto_amount = float(str(obs.metadata.to_dict().get("amount", 0.0)))

            # MarketService creates the offer
            payment_instructions, payment_uri = await self.market_service.create_offer(
                item_id=item_id,
                item_name=item_name,
                secret=neg_obs.accepted.reservation_code,
                price=crypto_amount,
                currency=self.settings.crypto.currency,
                buyer_did=agent_did,
                ttl_seconds=self.settings.crypto.deal_ttl_seconds,
            )

            neg_obs.accepted.reservation_code = ""  # Clear plain secret
            # Assuming payment_instructions has payment_memo
            neg_obs.accepted.crypto_payment = cast(Any, payment_instructions)
            neg_obs.payment_uri = payment_uri

            logger.info(
                "crypto_offer_created",
                deal_id=getattr(payment_instructions, "deal_id", "unknown"),
                amount=crypto_amount,
                currency=self.settings.crypto.currency,
            )

        except Exception as e:
            logger.warning("crypto_lock_failed", error=str(e), exc_info=True)
