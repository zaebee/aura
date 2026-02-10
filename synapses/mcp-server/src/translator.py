import uuid
from datetime import UTC, datetime
from typing import Any, cast

from aura_core import Observation
from aura_core.gen.aura.dna.v1 import (
    AgentIdentity,
    NegotiationSignal,
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
                signal_id=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_NEGOTIATION),
                timestamp=datetime.now(UTC),
                negotiation=NegotiationSignal(
                    identifier=kwargs.get("item_id", ""),
                    price=kwargs.get("bid", 0.0),
                    agent=AgentIdentity(
                        did=kwargs.get("agent_did", "mcp-agent"),
                        reputation=1.0,
                    ),
                ),
            )

        if tool_name == "search":
            # For search, we might use metadata to pass the query
            return Signal(
                signal_id=signal_id,
                signal_type=cast(
                    SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED
                ),  # TODO: Create a dedicated SIGNAL_TYPE_SEARCH
                timestamp=datetime.now(UTC),
                metadata={
                    "query": kwargs.get("query", ""),
                    "limit": str(kwargs.get("limit", 3)),
                    "intent": "search",
                },
            )

        return Signal(
            signal_id=signal_id,
            signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_UNSPECIFIED),
            timestamp=datetime.now(UTC),
        )

    def from_observation(self, observation: Observation) -> str:
        """Convert Hive Observation to LLM-friendly string."""
        if not observation.success:
            return f"❌ Operation failed: {observation.error or 'Unknown error'}"

        if not observation.negotiation:
            return "✅ Operation completed but returned no data."

        response = observation.negotiation

        if response.accepted:
            final_price = response.accepted.final_price
            return f"🎉 SUCCESS! Negotiation accepted at ${final_price:.2f}."
        elif response.countered:
            proposed_price = response.countered.proposed_price
            message = response.countered.human_message or "No reason provided."
            return f"🔄 COUNTER-OFFER: ${proposed_price:.2f}. Message: {message}"
        elif response.rejected:
            return f"🚫 REJECTED. Reason: {response.rejected.reason_code}"

        return "✅ Operation completed with unknown status."
