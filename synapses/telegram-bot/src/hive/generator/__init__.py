import time
from typing import Any

import structlog
from aura_core import Event, Generator, Observation, map_action
from aura_core.gen.aura.dna.v1 import ActionType, NegotiationEvent
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent
from opentelemetry import trace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramGenerator(Generator[Observation, Event]):
    """G - Generator: Emits events to NATS blood stream."""

    def __init__(self, nats_client: Any = None):
        self.nc = nats_client

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
                    from typing import cast

                    proto_event.negotiation = NegotiationEvent(
                        session_token=observation.metadata.get("session_token", ""),
                        action=cast(ActionType, map_action(action_name)),
                        price=observation.metadata.get("price", 0.0),
                        item_id=observation.metadata.get("item_id", ""),
                        agent_did=observation.metadata.get("agent_did", ""),
                    )

                event = Event(
                    topic=topic, payload=observation.metadata, timestamp=time.time()
                )
                events.append(event)

                span.set_attribute("event_topic", topic)
                logger.info("event_generated", topic=topic)

                if self.nc:
                    try:
                        binary_data = proto_event.SerializeToString()
                        await self.nc.publish(topic, binary_data)
                        logger.info(
                            "event_published_binary", topic=topic, size=len(binary_data)
                        )
                    except Exception as e:
                        logger.error("failed_to_publish_event", error=str(e))
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))

            return events
