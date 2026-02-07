from typing import Any

import structlog
from aura_core import Event, Generator, Observation
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramGenerator(Generator[Observation, Event]):
    """G - Generator: Emits events (heartbeats, transactions) via Pulse Protein."""

    def __init__(self, registry: Any, settings: Any = None) -> None:
        self.registry = registry
        self.settings = settings

    async def pulse(self, observation: Observation) -> list[Event]:
        """
        Generate events based on the observation and emit them via Pulse Protein.
        """
        from datetime import UTC, datetime
        with tracer.start_as_current_span("generator_pulse") as span:
            events = []
            now = datetime.now(UTC)

            # Determine event type based on observation
            event_type = observation.event_type
            if not event_type:
                if not observation.success:
                    event_type = "error"

            if event_type and "negotiation" in event_type:
                action_name = event_type.replace("negotiation_", "")
                session_token = observation.metadata.get("session_token", "unknown")
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

                # Metric Normalization
                if action_name in ["accept", "counter"]:
                    await self.registry.execute(
                        "telemetry",
                        "increment_counter",
                        {"name": "negotiation_accepted_total", "labels": {"service": "telegram"}}
                    )

                event = Event(
                    topic=f"aura.tg.{event_type}",
                    timestamp=now
                )
                event.metadata = {str(k): str(v) for k, v in observation.metadata.items()}
                events.append(event)
                span.set_attribute("event_topic", event.topic)

            # System Heartbeat
            await self.registry.execute("pulse", "emit_heartbeat", {"service": "telegram"})

            return events
