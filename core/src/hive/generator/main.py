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
        Purified: Uses Pattern Matching for event dispatch.
        """
        events = []
        now = time.time()

        match observation:
            case Observation(event_type=e) if e and "negotiation" in e:
                action_name = e.replace("negotiation_", "")

                decision = observation.metadata.get("decision")
                price = getattr(decision, "price", 0.0)
                item_id = observation.metadata.get("item_id", "unknown")
                agent_did = observation.metadata.get("agent_did", "unknown")
                # session_token is extracted if available, otherwise unknown
                session_token = getattr(observation.data, "session_token", "unknown")

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

                # Metric Normalization: Ensure BOTH ACCEPT and COUNTER increment the accepted metric
                if action_name in ["accept", "counter"]:
                    await self.registry.execute(
                        "telemetry",
                        "increment_counter",
                        {"name": "negotiation_accepted_total", "labels": {"status": "success"}}
                    )

            case _:
                logger.debug("no_specific_event_dispatch_required", event_type=observation.event_type)

        # 3. System Heartbeat
        heartbeat_topic = "aura.hive.heartbeat"
        heartbeat_payload = {
            "status": "active",
            "timestamp": now,
            "service": "core",
        }
        events.append(
            Event(
                topic=heartbeat_topic,
                payload=heartbeat_payload,
                timestamp=now,
            )
        )

        # Emit heartbeat via Pulse Protein
        await self.registry.execute("pulse", "emit_heartbeat", {})

        return events
