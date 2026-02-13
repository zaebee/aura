import json
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
from aura_core.gen.aura.core.v1 import (
    NegotiationObservation,
    OfferAccepted,
    OfferCountered,
    OfferRejected,
)
from aura_core.gen.aura.core.v1.google import protobuf

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
        This executes the decision and produces an observation (the gRPC response).
        """
        logger.debug("connector_act_started", action=action.action)

        action_name = action.action.name.lower().replace("action_type_", "")

        # 1. Handle Polymorphic Search
        if action_name == "evaluate" and action.asset and action.asset.asset_identifier == "search":
             return await self._handle_search(action, context)

        # 2. Map IntentAction to modular NegotiationObservation
        neg_obs = NegotiationObservation(
            item_identifier=context.hive.item_identifier if context.hive else "unknown",
            valid_until_timestamp=int(time.time() + 600),
        )

        price = action.negotiation.price if action.negotiation else 0.0
        message = action.negotiation.message if action.negotiation else ""

        if action_name == "accept":
            neg_obs.accepted = OfferAccepted(
                final_price=price,
                reservation_code=f"HIVE-{uuid.uuid4()}"
            )
        elif action_name == "counter":
            neg_obs.countered = OfferCountered(
                proposed_price=price,
                human_message=message,
                reason_code="NEGOTIATION_ONGOING"
            )
        elif action_name == "reject":
            neg_obs.rejected = OfferRejected(reason_code="OFFER_TOO_LOW")
        elif action_name == "ui_required":
            neg_obs.rejected = OfferRejected(reason_code="UI_REQUIRED")
        else:
            logger.error("unknown_action_type", action=action_name)
            neg_obs.rejected = OfferRejected(reason_code="INTERNAL_ERROR")

        # SSA Directive: native binary payload
        any_payload = protobuf.Any()
        any_payload.value = bytes(neg_obs)

        return Observation(
            success=True,
            payload=any_payload,
            event_type=f"negotiation_{action_name}",
            metadata={
                "item_id": context.hive.item_identifier if context.hive else "unknown",
                "agent_did": context.hive.offer.agent_did if context.hive else "unknown",
                "payment_uri": context.metadata.get("payment_uri", ""),
            },
        )

    async def _handle_search(self, action: IntentAction, context: HiveContext) -> Observation:
        query = action.asset.action_parameters.get("query", "")

        # 1. Generate Embedding
        embed_obs = await self.registry.execute(
            "reasoning", "generate_embedding", {"text": query}
        )
        if not embed_obs.success:
             return Observation(success=False, error=f"Embedding failed: {embed_obs.error}")

        # Unpack Vector from payload
        from aura_core.gen.aura.core.v1 import Vector
        vector_msg = Vector().parse(embed_obs.payload.value)

        # 2. Vector Search
        search_obs = await self.registry.execute(
            "persistence",
            "vector_search",
            {
                "query_vector": list(vector_msg.values),
                "limit": 5,
            },
        )

        if not search_obs.success:
             return Observation(success=False, error=f"Search failed: {search_obs.error}")

        # 3. Format results
        results = json.loads(search_obs.metadata.get("item_data", "[]"))

        # We can return the results in metadata for the bot to parse,
        # or we can use a custom observation.
        # Let's use AssetObservation as a container if it fits, or just JSON in metadata for multiple.

        return Observation(
            success=True,
            event_type="search_results",
            metadata={"item_data": json.dumps(results)}
        )
