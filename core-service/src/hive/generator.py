import json
import time

import nats.errors
import structlog
from hive.dna import Event, Observation

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveGenerator:
    """G - Generator: Emits events (heartbeats, transactions) to the Hive's blood stream (NATS)."""

    def __init__(self, nats_client=None):
        """
        Initialize the generator.

        Args:
            nats_client: An active nats-py client instance.
        """
        self.nc = nats_client
        self.settings = get_settings()

    async def pulse(self, observation: Observation) -> list[Event]:
        """
        Generate events based on the observation and emit them.

        Args:
            observation: The observation from the Connector.
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

            # Extract session token from Protobuf data if possible
            if hasattr(observation.data, "session_token"):
                payload["session_token"] = observation.data.session_token

            events.append(
                Event(
                    topic=f"aura.hive.events.{observation.event_type}",
                    payload=payload,
                    timestamp=now,
                )
            )

        # 2. System Heartbeat
        events.append(
            Event(
                topic="aura.hive.heartbeat",
                payload={
                    "status": "active",
                    "timestamp": now,
                    "service": "core-service",
                },
                timestamp=now,
            )
        )

        # 3. Emit to NATS
        if self.nc and self.nc.is_connected:
            for event in events:
                try:
                    await self.nc.publish(
                        event.topic, json.dumps(event.payload).encode()
                    )
                except (
                    nats.errors.ErrConnectionClosed,
                    nats.errors.ErrTimeout,
                ) as e:
                    logger.error("nats_publish_failed", topic=event.topic, error=str(e))
        else:
            logger.debug("nats_not_connected_skipping_emit")

        return events
