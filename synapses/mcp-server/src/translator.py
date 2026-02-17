import uuid
from datetime import UTC, datetime
from typing import Any, cast

import betterproto
from aura_core_gen.aura.core.v1 import (
    AgentIdentity,
    NegotiationSignal,
    Observation,
    Signal,
    SignalType,
)


class MCPTranslator:
    """Standardized translator for MCP tool calls and Hive observations."""

    def to_signal(self, tool_name: str, **kwargs: Any) -> Signal:
        """Convert MCP tool call to universal Signal protobuf."""
        signal_id = str(uuid.uuid4())

        if tool_name == "negotiate":
            return Signal(
                identifier=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_NEGOTIATION),
                timestamp=datetime.now(UTC),
                negotiation=NegotiationSignal(
                    item_identifier=kwargs.get("item_id", ""),
                    bid_amount=kwargs.get("bid", 0.0),
                    agent=AgentIdentity(
                        did=kwargs.get("agent_did", "mcp-agent"),
                        reputation_score=1.0,
                    ),
                ),
            )

        if tool_name == "search":
            sig = Signal(
                identifier=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED),
                timestamp=datetime.now(UTC),
            )
            sig.metadata.from_dict(
                {
                    "query": str(kwargs.get("query", "")),
                    "limit": str(kwargs.get("limit", 3)),
                    "intent": "search",
                }
            )
            return sig

        return Signal(
            identifier=signal_id,
            signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED),
            timestamp=datetime.now(UTC),
        )

    def from_observation(self, observation: Observation) -> str:
        """Convert Hive Observation to LLM-friendly string."""
        if not observation.success:
            return f"❌ Operation failed: {observation.error or 'Unknown error'}"

        if not observation.negotiation:
            return "✅ Operation completed but returned no negotiation data."

        neg = observation.negotiation
        res_name, res_val = betterproto.which_one_of(neg, "result")

        if res_name == "accepted" and res_val:
            final_price = getattr(res_val, "final_price", 0.0)
            return f"🎉 SUCCESS! Negotiation accepted at ${final_price:.2f}."
        elif res_name == "countered" and res_val:
            proposed_price = getattr(res_val, "proposed_price", 0.0)
            message = getattr(res_val, "human_message", "No reason provided.")
            return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"
        elif res_name == "rejected" and res_val:
            reason_code = getattr(res_val, "reason_code", "UNKNOWN")
            return f"🚫 REJECTED. Reason: {reason_code}"

        # Note: UI Required is now mapped to rejected with reason UI_REQUIRED in connector
        return f"✅ Operation completed with status: {res_name}"
