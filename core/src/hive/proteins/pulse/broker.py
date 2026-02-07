"""
Pulse Protein Internal - NATS JetStream Provider for Binary Bloodstream.

Handles binary proto serialization and JetStream publishing.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import nats
import nats.errors
from google.protobuf.timestamp_pb2 import Timestamp

from hive.proto.aura.dna.v1 import dna_pb2

logger = logging.getLogger(__name__)


class JetStreamProvider:
    """
    JetStream provider for binary proto message publishing.

    Replaces JSON-over-NATS with strictly typed binary protobuf messages.
    """

    def __init__(self, nats_url: str):
        self.nats_url = nats_url
        self.nc: nats.NATS | None = None
        self.js: nats.js.JetStreamContext | None = None

    async def connect(self) -> bool:
        """Connect to NATS and initialize JetStream context."""
        try:
            nc = await nats.connect(self.nats_url)
            self.nc = nc
            self.js = nc.jetstream()
            logger.info(f"Connected to NATS JetStream at {self.nats_url}")
            return True
        except nats.errors.NoServersError as e:
            logger.warning(f"NATS connection failed (no servers): {e}")
            return False
        except Exception as e:
            logger.warning(f"NATS connection failed: {e}")
            return False

    def _create_timestamp(self) -> Timestamp:
        """Create a protobuf Timestamp for now."""
        ts = Timestamp()
        ts.FromDatetime(datetime.now(UTC))
        return ts

    def _create_trace_context(self, trace_id: str | None = None, span_id: str | None = None) -> dna_pb2.TraceContext:
        """Create trace context for OTel propagation."""
        trace = dna_pb2.TraceContext()
        trace.trace_id = trace_id or uuid.uuid4().hex
        trace.span_id = span_id or uuid.uuid4().hex[:16]
        trace.trace_flags = "01"  # Sampled
        return trace

    async def publish_negotiation_event(
        self,
        session_token: str,
        action: str,
        price: float,
        item_id: str,
        agent_did: str,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish a negotiation event as binary proto."""
        if not self.js:
            logger.warning("JetStream not connected, skipping publish")
            return False

        try:
            event = dna_pb2.Event()
            event.event_id = f"neg-{uuid.uuid4().hex[:8]}"
            event.topic = f"aura.hive.events.negotiation_{action}"
            event.timestamp.CopyFrom(self._create_timestamp())
            event.trace.CopyFrom(self._create_trace_context(trace_id, span_id))

            # Set negotiation payload
            event.negotiation.session_token = session_token
            event.negotiation.action = self._action_to_enum(action)  # type: ignore[assignment]
            event.negotiation.price = price
            event.negotiation.item_id = item_id
            event.negotiation.agent_did = agent_did

            # Serialize and publish
            binary_data = event.SerializeToString()
            ack = await self.js.publish(event.topic, binary_data)

            logger.debug(f"Published negotiation event: stream={ack.stream}, seq={ack.seq}, bytes={len(binary_data)}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish negotiation event: {e}")
            return False

    async def publish_heartbeat(
        self,
        service: str = "core",
        instance_id: str | None = None,
        status: str = "ok",
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish a heartbeat event as binary proto."""
        if not self.js:
            logger.warning("JetStream not connected, skipping heartbeat")
            return False

        try:
            event = dna_pb2.Event()
            event.event_id = f"hb-{uuid.uuid4().hex[:8]}"
            event.topic = "aura.hive.heartbeat"
            event.timestamp.CopyFrom(self._create_timestamp())
            event.trace.CopyFrom(self._create_trace_context(trace_id, span_id))

            # Set heartbeat payload
            event.heartbeat.service = service
            event.heartbeat.instance_id = instance_id or uuid.uuid4().hex[:8]
            event.heartbeat.status = self._status_to_enum(status)  # type: ignore[assignment]

            # Serialize and publish
            binary_data = event.SerializeToString()
            ack = await self.js.publish(event.topic, binary_data)

            logger.debug(f"Published heartbeat: stream={ack.stream}, seq={ack.seq}, bytes={len(binary_data)}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish heartbeat: {e}")
            return False

    async def publish_vitals(
        self,
        service: str,
        cpu_usage: float,
        memory_usage: float,
        status: str = "ok",
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish system vitals as binary proto."""
        if not self.js:
            return False

        try:
            event = dna_pb2.Event()
            event.event_id = f"vit-{uuid.uuid4().hex[:8]}"
            event.topic = f"aura.hive.vitals.{service}"
            event.timestamp.CopyFrom(self._create_timestamp())
            event.trace.CopyFrom(self._create_trace_context(trace_id, span_id))

            # Set vitals payload
            event.vitals.service = service
            event.vitals.status = self._status_to_enum(status)  # type: ignore[assignment]
            event.vitals.cpu_usage_percent = cpu_usage
            event.vitals.memory_usage_mb = memory_usage

            binary_data = event.SerializeToString()
            ack = await self.js.publish(event.topic, binary_data)

            logger.debug(f"Published vitals: stream={ack.stream}, seq={ack.seq}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish vitals: {e}")
            return False

    async def publish_alert(
        self,
        severity: str,
        message: str,
        source: str,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish an alert event as binary proto."""
        if not self.js:
            return False

        try:
            event = dna_pb2.Event()
            event.event_id = f"alert-{uuid.uuid4().hex[:8]}"
            event.topic = f"aura.hive.events.alert_{severity}"
            event.timestamp.CopyFrom(self._create_timestamp())
            event.trace.CopyFrom(self._create_trace_context(trace_id, span_id))

            # Set alert payload
            event.alert.severity = self._severity_to_enum(severity)  # type: ignore[assignment]
            event.alert.message = message
            event.alert.source = source

            binary_data = event.SerializeToString()
            ack = await self.js.publish(event.topic, binary_data)

            logger.debug(f"Published alert: stream={ack.stream}, seq={ack.seq}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish alert: {e}")
            return False

    async def publish_audit(
        self,
        repo_name: str,
        is_pure: bool,
        heresies: list[str],
        negotiation_success_rate: float,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish an audit event as binary proto."""
        if not self.js:
            return False

        try:
            event = dna_pb2.Event()
            event.event_id = f"audit-{uuid.uuid4().hex[:8]}"
            event.topic = "aura.hive.audit.report"
            event.timestamp.CopyFrom(self._create_timestamp())
            event.trace.CopyFrom(self._create_trace_context(trace_id, span_id))

            # Set audit payload
            event.audit.repo_name = repo_name
            event.audit.is_pure = is_pure
            event.audit.heresies.extend(heresies)
            event.audit.negotiation_success_rate = negotiation_success_rate

            binary_data = event.SerializeToString()
            ack = await self.js.publish(event.topic, binary_data)

            logger.debug(f"Published audit: stream={ack.stream}, seq={ack.seq}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish audit: {e}")
            return False

    async def publish_raw(self, topic: str, payload: dict[str, Any]) -> bool:
        """
        Fallback: Publish raw event (for backward compatibility).

        DEPRECATED: Use typed publish methods instead.
        """
        if not self.js:
            return False

        try:
            import json
            data = json.dumps(payload).encode()
            ack = await self.js.publish(topic, data)
            logger.warning(f"Published raw JSON (deprecated): {topic}, seq={ack.seq}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish raw: {e}")
            return False

    async def close(self) -> None:
        """Close NATS connection."""
        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")

    def _action_to_enum(self, action: str) -> int:
        """Convert action string to ActionType enum."""
        mapping = {
            "accept": dna_pb2.ACTION_TYPE_ACCEPT,
            "counter": dna_pb2.ACTION_TYPE_COUNTER,
            "reject": dna_pb2.ACTION_TYPE_REJECT,
            "audit": dna_pb2.ACTION_TYPE_AUDIT,
            "ui_required": dna_pb2.ACTION_TYPE_UI_REQUIRED,
            "error": dna_pb2.ACTION_TYPE_ERROR,
        }
        return mapping.get(action.lower(), dna_pb2.ACTION_TYPE_UNSPECIFIED)

    def _status_to_enum(self, status: str) -> int:
        """Convert status string to VitalsStatus enum."""
        mapping = {
            "ok": dna_pb2.VITALS_STATUS_OK,
            "degraded": dna_pb2.VITALS_STATUS_DEGRADED,
            "error": dna_pb2.VITALS_STATUS_ERROR,
        }
        return mapping.get(status.lower(), dna_pb2.VITALS_STATUS_UNSPECIFIED)

    def _severity_to_enum(self, severity: str) -> int:
        """Convert severity string to AlertSeverity enum."""
        mapping = {
            "info": dna_pb2.ALERT_SEVERITY_INFO,
            "warning": dna_pb2.ALERT_SEVERITY_WARNING,
            "error": dna_pb2.ALERT_SEVERITY_ERROR,
            "critical": dna_pb2.ALERT_SEVERITY_CRITICAL,
        }
        return mapping.get(severity.lower(), dna_pb2.ALERT_SEVERITY_UNSPECIFIED)


class JetStreamSubscriber:
    """
    JetStream subscriber for consuming binary proto messages.

    Used by the Aggregator to "breathe in" events from the bloodstream.
    """

    def __init__(self, nats_url: str):
        self.nats_url = nats_url
        self.nc: nats.NATS | None = None
        self.js: nats.js.JetStreamContext | None = None
        self._subscriptions: dict[str, Any] = {}

    async def connect(self) -> bool:
        """Connect to NATS and initialize JetStream context."""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            logger.info(f"Subscriber connected to NATS JetStream at {self.nats_url}")
            return True
        except Exception as e:
            logger.warning(f"Subscriber connection failed: {e}")
            return False

    async def subscribe(
        self,
        stream: str,
        consumer: str,
        callback: Any,
    ) -> bool:
        """
        Subscribe to a JetStream consumer and process binary proto messages.

        Args:
            stream: Stream name (e.g., "AURA_EVENTS")
            consumer: Durable consumer name (e.g., "core-processor")
            callback: Async function(event: dna_pb2.Event) -> None
        """
        if not self.js:
            return False

        try:
            # Pull-based subscription for reliability
            psub = await self.js.pull_subscribe(
                subject="",  # Consumer defines the filter
                durable=consumer,
                stream=stream,
            )
            self._subscriptions[f"{stream}:{consumer}"] = psub

            logger.info(f"Subscribed to {stream}:{consumer}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False

    async def fetch_events(
        self,
        stream: str,
        consumer: str,
        batch: int = 10,
        timeout: float = 1.0,
    ) -> list[dna_pb2.Event]:
        """
        Fetch a batch of binary proto events from a consumer.

        Returns deserialized Event proto objects.
        """
        key = f"{stream}:{consumer}"
        psub = self._subscriptions.get(key)

        if not psub:
            logger.warning(f"No subscription for {key}")
            return []

        events = []
        try:
            msgs = await psub.fetch(batch=batch, timeout=timeout)

            for msg in msgs:
                try:
                    event = dna_pb2.Event()
                    event.ParseFromString(msg.data)
                    events.append(event)
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Failed to parse event: {e}")
                    # NAK for redelivery
                    await msg.nak()

            return events

        except nats.errors.TimeoutError:
            # No messages available, not an error
            return []
        except Exception as e:
            logger.error(f"Failed to fetch events: {e}")
            return []

    async def close(self) -> None:
        """Close all subscriptions and NATS connection."""
        for _key, psub in self._subscriptions.items():
            try:
                await psub.unsubscribe()
            except Exception:  # nosec B110
                pass  # Ignore errors during cleanup
        self._subscriptions.clear()

        if self.nc:
            await self.nc.close()
            logger.info("Subscriber connection closed")


# Backward compatibility alias
NatsProvider = JetStreamProvider
