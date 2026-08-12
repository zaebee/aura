import time
import uuid
from typing import Any, cast

import betterproto
import structlog
from aura_core import (
    BaseConnector,
    SkillRegistry,
    make_struct,
)
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


def _get_hive(context: Context) -> Any:
    """Safely extract HiveContextData from Context.data oneof — returns None for non-hive contexts."""
    name, value = betterproto.which_one_of(context, "data")
    return value if name == "hive" else None


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

        hive = _get_hive(context)
        neg_obs = NegotiationObservation(
            item_identifier=hive.item_identifier if hive else context.identifier,
            valid_until_timestamp=int(time.time() + 600),
        )

        # Copied before the result branches, so no branch can be the one that
        # forgets. The chain out to the client re-assembles each message field
        # by field rather than passing it along, and the receipt died here —
        # NegotiationObservation had nowhere to put it.
        #
        # It is the dispute token that travels now, not the receipt. The receipt
        # is addressed to an auditor and stops at the Membrane's structured log;
        # what the counterparty gets is a handle the auditor resolves.
        neg_obs.dispute_token = action.dispute_token

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

        await self._record_turn(action, context, neg_intent, event_type)

        obs_meta = _get_metadata_dict(context)
        obs_meta.update(
            {
                "item_id": str(hive.item_identifier if hive else context.identifier),
                "agent_did": str(
                    hive.offer.agent_did if hive and hive.offer else "unknown"
                ),
                "payment_uri": str(neg_obs.payment_uri or ""),
            }
        )

        return Observation(
            success=True,
            negotiation=neg_obs,
            event_type=event_type,
            trace=context.trace,
            metadata=make_struct(obs_meta),
        )

    async def _record_turn(
        self,
        action: Intent,
        context: Context,
        neg_intent: Any,
        event_type: str,
    ) -> None:
        """
        Append this round to the conversation, so the next one can see it.

        Recorded here rather than in the Transformer because this is the
        decision that actually went out — post-Membrane. A history of what the
        model wanted would teach it nothing about what the guard allowed, and
        the override rate is precisely what we want to be able to read later.
        """
        try:
            hive = _get_hive(context)
            offer = getattr(hive, "offer", None) if hive else None
            agent_did = getattr(offer, "agent_did", "") if offer else ""
            item_id = getattr(hive, "item_identifier", "") if hive else ""
            if not agent_did or not item_id:
                return
        except Exception:
            return

        reasoning = action.reasoning or ""
        turn = {
            "action": event_type,
            "bid": float(getattr(offer, "bid_amount", 0.0) or 0.0),
            "price": float(getattr(neg_intent, "price", 0.0) or 0.0)
            if neg_intent
            else 0.0,
            "message": str(getattr(neg_intent, "message", "") or "")[:280],
            # The guard leaves this marker when it replaces a decision. Carrying
            # it forward is what makes the override rate measurable per round.
            "membrane_override": "Membrane Override" in reasoning,
            "agent_did": agent_did,
            "item_id": item_id,
        }

        try:
            obs = await self.registry.execute(
                "persistence",
                "append_negotiation_turn",
                {"agent_did": agent_did, "item_id": item_id, "turn": turn},
            )
            # The registry reports a skill failure by returning success=False,
            # not by raising, so an except block alone would swallow it.
            if not obs.success:
                logger.warning("negotiation_turn_not_recorded", error=obs.error)
        except Exception as e:
            # A negotiation must not fail because its transcript could not be
            # written. Losing a turn degrades the next prompt; raising loses the deal.
            logger.warning("negotiation_turn_not_recorded", error=str(e))

    async def _handle_crypto_lock(
        self,
        neg_obs: NegotiationObservation,
        action: Intent,
        context: Context,
    ) -> None:
        """Encrypts the reservation code and creates a locked deal via Skills/MarketService."""
        try:
            hive = _get_hive(context)
            item_id = hive.item_identifier if hive else context.identifier
            item_name = str(context.metadata.to_dict().get("item_name", "Aura Item"))
            params_name, params_value = betterproto.which_one_of(action, "params")
            neg_intent = params_value if params_name == "negotiation" else None
            price = neg_intent.price if neg_intent else 0.0
            agent_did = hive.offer.agent_did if hive and hive.offer else "unknown"

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
