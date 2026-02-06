import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aura_core import IntentAction, Observation, SkillRegistry
from aura_core.gen.aura.dna.v1 import ActionType
from hive.proto.aura.negotiation.v1 import negotiation_pb2

from config import settings

logger = structlog.get_logger(__name__)

DEFAULT_UNKNOWN_ITEM_ID = "unknown_item"
DEFAULT_UNKNOWN_SOLANA_ADDRESS = "unknown_address"
DEFAULT_UNKNOWN_AGENT_DID = "did:unknown"
DEFAULT_ITEM_NAME = "Aura Item"


async def act(
    action: IntentAction, registry: SkillRegistry, context: Any = None
) -> Observation:
    """
    The Motor: Executes actions using real Proteins and maps to gRPC.
    - Uses 'transaction' Skill (Solana)
    - Uses 'persistence' Skill (Storage)
    - Returns NegotiateResponse proto in Observation.data
    """
    # 1. Extract action name for logging and event_type
    action_val = action.action
    if isinstance(action_val, ActionType):
        raw_action_name = action_val.name
    else:
        raw_action_name = str(action_val)

    action_name = str(raw_action_name).lower().replace("action_type_", "")
    event_type = f"negotiation_{action_name}"

    logger.info("chamber_act", action=action_name, price=action.price)

    # 2. Initialize gRPC Response
    response = negotiation_pb2.NegotiateResponse()
    response.session_token = "sess_" + (
        getattr(context, "request_id", str(uuid.uuid4()))
        if context
        else str(uuid.uuid4())
    )
    obs_data: dict[str, Any] = {}

    # 3. Map IntentAction to gRPC and Proteins
    if action.action == ActionType.ACTION_TYPE_ACCEPT:
        logger.info("chamber_finalizing_deal")
        response.accepted.final_price = action.price
        response.accepted.reservation_code = f"HIVE-{uuid.uuid4()}"

        # Hydrate persistence (Storage) to create the deal
        deal_id = str(uuid.uuid4())
        ttl_seconds = settings.crypto.deal_ttl_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        deal_params = {
            "id": deal_id,
            "item_id": context.item_id if context else DEFAULT_UNKNOWN_ITEM_ID,
            "item_name": (
                context.item_data.get("name", DEFAULT_ITEM_NAME)
                if context and context.item_data
                else DEFAULT_ITEM_NAME
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
        solana_address = addr_obs.data if addr_obs.success else DEFAULT_UNKNOWN_SOLANA_ADDRESS

        obs_data = {"deal_id": deal_id, "solana_address": solana_address}
        event_type = "negotiation_accepted"

    elif action.action == ActionType.ACTION_TYPE_COUNTER:
        response.countered.proposed_price = action.price
        response.countered.human_message = action.message

    elif action.action == ActionType.ACTION_TYPE_REJECT:
        response.rejected.reason_code = "OFFER_TOO_LOW"

    # 4. Final Observation
    return Observation(
        success=True,
        data=response,
        event_type=event_type,
        metadata={
            "price": action.price,
            "session_token": response.session_token,
            "item_id": context.item_id if context else DEFAULT_UNKNOWN_ITEM_ID,
            "agent_did": (
                context.offer.agent_did if context else DEFAULT_UNKNOWN_AGENT_DID
            ),
            **obs_data,
        },
    )
