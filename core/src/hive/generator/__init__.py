import time

import structlog
from aura_core import Event, Generator, Observation, SkillRegistry

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveGenerator(Generator[Observation, Event]):
    """G - Generator: Emits events (heartbeats, transactions) via Pulse Protein."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry
        self.settings = get_settings()

    async def pulse(self, observation: Observation) -> list[Event]:
        """
        Generate events based on the observation and emit them via Pulse Protein.
        """
        events = []
        now = time.time()

        # 1. Negotiation Event
        if observation.event_type:
            payload = {
                "success": observation.success,
                "event_type": observation.event_type,
                "timestamp": now,
            }

            if hasattr(observation.data, "session_token"):
                payload["session_token"] = observation.data.session_token

            topic = f"aura.hive.events.{observation.event_type}"
            events.append(
                Event(
                    topic=topic,
                    payload=payload,
                    timestamp=now,
                )
            )

            # Emit via Pulse Protein
            await self.registry.execute(
                "pulse", "emit_event", {"topic": topic, "payload": payload}
            )

        # 2. System Heartbeat
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
