import uuid
from datetime import UTC, datetime
from typing import Any

import betterproto
from aura_core.gen.aura.core.v1 import (
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
                signal_type=SignalType.SIGNAL_TYPE_NEGOTIATION,
                timestamp=datetime.now(UTC),
                negotiation=NegotiationSignal(
                    item_identifier=kwargs.get("item_id", ""),
                    bid_amount=kwargs.get("bid", 0.0),
                    agent=AgentIdentity(
                        did=kwargs.get("agent_did", "mcp-agent"),
                        reputation=1.0,
                    ),
                ),
            )

        if tool_name == "search":
            return Signal(
                identifier=signal_id,
                signal_type=SignalType.SIGNAL_TYPE_UNSPECIFIED,
                timestamp=datetime.now(UTC),
                metadata={
                    "query": kwargs.get("query", ""),
                    "limit": str(kwargs.get("limit", 3)),
                    "intent": "search",
                },
            )

        return Signal(
            identifier=signal_id,
            signal_type=SignalType.SIGNAL_TYPE_UNSPECIFIED,
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

        if res_name == "accepted":
            final_price = res_val.final_price
            return f"🎉 SUCCESS! Negotiation accepted at ${final_price:.2f}."
        elif res_name == "countered":
            proposed_price = res_val.proposed_price
            message = res_val.human_message or "No reason provided."
            return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"
        elif res_name == "rejected":
            return f"🚫 REJECTED. Reason: {res_val.reason_code}"

        # Note: UI Required is now mapped to rejected with reason UI_REQUIRED in connector
        return f"✅ Operation completed with status: {res_name}"
