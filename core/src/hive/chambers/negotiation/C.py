import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aura_core import IntentAction, Observation, SkillRegistry
from aura_core.gen.aura.dna.v1 import ActionType
from hive.proto.aura.negotiation.v1 import negotiation_pb2

logger = structlog.get_logger(__name__)


async def act(
    action: IntentAction, registry: SkillRegistry, context: Any = None
) -> Observation:
    """
    The Motor: Executes actions using real Proteins and maps to gRPC.
    - Uses 'transaction' Skill (Solana)
    - Uses 'persistence' Skill (Storage)
    - Returns NegotiateResponse proto in Observation.data
    """
    logger.info("chamber_act", action=str(action.action), price=action.price)

    # 1. Initialize gRPC Response
    response = negotiation_pb2.NegotiateResponse()
    response.session_token = "sess_" + (
        getattr(context, "request_id", str(uuid.uuid4()))
        if context
        else str(uuid.uuid4())
    )

    event_type = f"negotiation_{str(action.action).lower()}"
    obs_data: dict[str, Any] = {}

    # 2. Map IntentAction to gRPC and Proteins
    if action.action == ActionType.ACTION_TYPE_ACCEPT:
        logger.info("chamber_finalizing_deal")
        response.accepted.final_price = action.price
        response.accepted.reservation_code = f"HIVE-{uuid.uuid4()}"

        # Hydrate persistence (Storage) to create the deal
        deal_id = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(minutes=10)

        deal_params = {
            "id": deal_id,
            "item_id": context.item_id if context else "unknown",
            "item_name": (
                context.item_data.get("name", "Aura Item")
                if context and context.item_data
                else "Aura Item"
            ),
            "final_price": action.price,
            "currency": "USD",
            "payment_memo": f"aura-{deal_id[:8]}",
            "secret_content": response.accepted.reservation_code,
            "expires_at": expires_at,
        }
        await registry.execute("persistence", "create_deal", deal_params)

        # Hydrate transaction (Solana)
        addr_obs = await registry.execute("transaction", "get_address", {})
        solana_address = addr_obs.data if addr_obs.success else "unknown"

        obs_data = {"deal_id": deal_id, "solana_address": solana_address}
        event_type = "negotiation_accepted"

    elif action.action == ActionType.ACTION_TYPE_COUNTER:
        response.countered.proposed_price = action.price
        response.countered.human_message = action.message

    elif action.action == ActionType.ACTION_TYPE_REJECT:
        response.rejected.reason_code = "OFFER_TOO_LOW"

    # 3. Final Observation
    return Observation(
        success=True,
        data=response,
        event_type=event_type,
        metadata={
            "price": action.price,
            "session_token": response.session_token,
            "item_id": context.item_id if context else "unknown",
            "agent_did": context.offer.agent_did if context else "unknown",
            **obs_data,
        },
    )
