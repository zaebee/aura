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
                    item_id=kwargs.get("item_id", ""),
                    bid_amount=kwargs.get("bid", 0.0),
                    agent=AgentIdentity(
                        did=kwargs.get("agent_did", "mcp-agent"),
                        reputation_score=1.0,
                    ),
                ),
            )

        if tool_name == "search":
            # For search, we might use metadata to pass the query
            return Signal(
                signal_id=signal_id,
                signal_type=cast(SignalType, SignalType.SIGNAL_TYPE_NEGOTIATION),  # Generic negotiation flow for now
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
            return f"❌ Operation failed: {observation.error}"

        data = observation.data
        # If it's a gRPC response or internal dict
        if hasattr(data, "status"):
            status = data.status
        elif isinstance(data, dict):
            status = data.get("status")
        else:
            status = "unknown"

        if status == "accepted":
            return "🎉 SUCCESS! Negotiation accepted."
        elif status == "countered":
            return "🔄 COUNTER-OFFER received."

        return f"✅ Operation completed: {observation.message_id or 'ok'}"
