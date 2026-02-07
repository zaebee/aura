import time
from typing import Any

import structlog
from aura_core import Event, Generator, Observation, SkillRegistry

logger = structlog.get_logger(__name__)


class HiveGenerator(Generator[Observation, Event]):
    """G - Generator: Emits events (heartbeats, transactions) via Pulse Protein."""

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.registry = registry
        self.settings = settings

    async def pulse(self, observation: Observation) -> list[Event]:
        """
        Generate events based on the observation and emit them via Pulse Protein.
        """
        from datetime import UTC, datetime
        events = []
        now = datetime.now(UTC)

        # 1. Negotiation Event (Binary Bloodstream)
        if observation.event_type and "negotiation" in observation.event_type:
            action_name = observation.event_type.replace("negotiation_", "")
            session_token = "unknown"
            if observation.negotiation:
                session_token = observation.negotiation.session_token

            price = float(observation.metadata.get("price", 0.0))
            item_id = observation.metadata.get("item_id", "unknown")
            agent_did = observation.metadata.get("agent_did", "unknown")

            # Emit via Pulse Protein using binary emit_negotiation
            await self.registry.execute(
                "pulse",
                "emit_negotiation",
                {
                    "session_token": session_token,
                    "action": action_name,
                    "price": price,
                    "item_id": item_id,
                    "agent_did": agent_did,
                }
            )

            # 2. Metric Normalization (The 0.0 Success Rate Fix)
            # Ensure BOTH ACCEPT and COUNTER increment the accepted metric
            if action_name in ["accept", "counter"]:
                await self.registry.execute(
                    "telemetry",
                    "increment_counter",
                    {"name": "negotiation_accepted_total", "labels": {"status": "success"}}
                )

        # 3. System Heartbeat
        # In the new architecture, we emit a proto event
        heartbeat_event = Event(
            topic="aura.hive.heartbeat",
            timestamp=now,
        )
        # We don't have a generic payload anymore, but we can use metadata
        heartbeat_event.metadata = {"status": "active", "service": "core"}
        events.append(heartbeat_event)

        # Emit heartbeat via Pulse Protein
        await self.registry.execute("pulse", "emit_heartbeat", {})

        return events
