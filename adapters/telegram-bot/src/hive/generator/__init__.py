import time
from typing import Any

import structlog
from aura_core import Event, Generator, Observation
from aura_core.gen.aura.dna.v1 import ActionType, NegotiationEvent
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramGenerator(Generator[Observation, Event]):
    """G - Generator: Emits events to NATS blood stream."""

    def __init__(self, nats_client: Any = None):
        self.nc = nats_client

    def _map_action(self, action_str: str) -> ActionType:
        """Map action string to ActionType enum."""
        from typing import cast

        mapping = {
            "accept": ActionType.ACTION_TYPE_ACCEPT,
            "counter": ActionType.ACTION_TYPE_COUNTER,
            "reject": ActionType.ACTION_TYPE_REJECT,
            "ui_required": ActionType.ACTION_TYPE_UI_REQUIRED,
            "error": ActionType.ACTION_TYPE_ERROR,
        }
        val = mapping.get(action_str.lower(), ActionType.ACTION_TYPE_UNSPECIFIED)
        return cast(ActionType, val)

    async def pulse(self, observation: Observation) -> list[Event]:
        with tracer.start_as_current_span("generator_pulse") as span:
            events = []

            # Determine event type based on observation
            event_type = observation.event_type
            if not event_type:
                if not observation.success:
                    event_type = "error"
                # Other types should be set by the caller in metadata or event_type

            if event_type:
                topic = f"aura.tg.{event_type}"

                # Create binary proto event (Binary Bloodstream)
                proto_event = ProtoEvent()
                proto_event.topic = topic
                # timestamp is handled by betterproto datetime or manual set

                if "negotiation" in event_type:
                    action_name = event_type.replace("negotiation_", "")
                    proto_event.negotiation = NegotiationEvent(
                        session_token=observation.metadata.get("session_token", ""),
                        action=self._map_action(action_name),
                        price=observation.metadata.get("price", 0.0),
                        item_id=observation.metadata.get("item_id", ""),
                        agent_did=observation.metadata.get("agent_did", ""),
                    )

                event = Event(
                    topic=topic,
                    payload=observation.metadata,
                    timestamp=time.time()
                )
                events.append(event)

                span.set_attribute("event_topic", topic)
                logger.info("event_generated", topic=topic)

                if self.nc:
                    try:
                        binary_data = proto_event.SerializeToString()
                        await self.nc.publish(topic, binary_data)
                        logger.info("event_published_binary", topic=topic, size=len(binary_data))
                    except Exception as e:
                        logger.error("failed_to_publish_event", error=str(e))
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

            return events
