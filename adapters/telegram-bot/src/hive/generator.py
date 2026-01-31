import json
import time
from typing import Any

import structlog
from opentelemetry import trace

from .dna import Event, Observation

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class TelegramGenerator:
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
                payload = {
                    "success": observation.success,
                    "error": observation.error,
                    **observation.metadata,
                }
                event = Event(topic=topic, payload=payload, timestamp=time.time())
                events.append(event)

                span.set_attribute("event_topic", topic)
                logger.info("event_generated", topic=topic)

                if self.nc:
                    try:
                        await self.nc.publish(topic, json.dumps(payload).encode())
                        logger.info("event_published", topic=topic)
                    except Exception as e:
                        logger.error("failed_to_publish_event", error=str(e))

            return events
