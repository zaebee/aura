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
from aura_core.gen.aura.core.v1 import (
    ActionType,
    AlertEvent,
    AuditEvent,
    Event,
    HeartbeatEvent,
    NegotiationEvent,
    Severity,
    Status,
    TraceContext,
    VitalsEvent,
)

from hive.metabolism.security import AuditSigner

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
        self.signer: AuditSigner | None = None

    def set_signer(self, signer: AuditSigner) -> None:
        """Set the AuditSigner for event signing."""
        self.signer = signer

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

    def _create_trace_context(
        self, trace_id: str | None = None, span_id: str | None = None
    ) -> TraceContext:
        """Create trace context for OTel propagation."""
        return TraceContext(
            trace_id=trace_id or uuid.uuid4().hex,
            span_id=span_id or uuid.uuid4().hex[:16],
            trace_flags="01"
        )

    async def _publish(self, topic: str, event: Event) -> bool:
        """Internal publish helper with optional signing."""
        if not self.js:
             return False

        binary_data = bytes(event)
        headers = None

        if self.signer:
            timestamp_iso = datetime.now(UTC).isoformat()
            headers = self.signer.make_headers(topic, binary_data, timestamp_iso)

        ack = await self.js.publish(topic, binary_data, headers=headers)
        logger.debug(f"Published to {topic}: stream={ack.stream}, seq={ack.seq}")
        return True

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
        try:
            event = Event(
                identifier=f"neg-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.events.negotiation_{action}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                negotiation=NegotiationEvent(
                    item_identifier=item_id,
                    action=self._action_to_enum(action),
                    price=price
                )
            )

            return await self._publish(event.topic, event)

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
        try:
            event = Event(
                identifier=f"hb-{uuid.uuid4().hex[:8]}",
                topic="aura.hive.heartbeat",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                heartbeat=HeartbeatEvent(
                    service=service,
                    instance_id=instance_id or uuid.uuid4().hex[:8],
                    status=self._status_to_enum(status)
                )
            )

            return await self._publish(event.topic, event)

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
        try:
            event = Event(
                identifier=f"vit-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.vitals.{service}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                vitals=VitalsEvent(
                    service=service,
                    status=self._status_to_enum(status),
                    cpu_usage_percent=cpu_usage,
                    memory_usage_mb=memory_usage
                )
            )

            return await self._publish(event.topic, event)

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
        try:
            event = Event(
                identifier=f"alert-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.events.alert_{severity}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                alert=AlertEvent(
                    severity=self._severity_to_enum(severity),
                    message=message,
                    source=source
                )
            )

            return await self._publish(event.topic, event)

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
        try:
            event = Event(
                identifier=f"audit-{uuid.uuid4().hex[:8]}",
                topic="aura.hive.audit.report",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                audit=AuditEvent(
                    repo_name=repo_name,
                    is_pure=is_pure,
                    heresies=heresies,
                    negotiation_success_rate=negotiation_success_rate
                )
            )

            return await self._publish(event.topic, event)

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

    def _action_to_enum(self, action: str) -> ActionType:
        """Convert action string to ActionType enum."""
        mapping: dict[str, ActionType] = {
            "accept": ActionType.ACTION_TYPE_ACCEPT,
            "counter": ActionType.ACTION_TYPE_COUNTER,
            "reject": ActionType.ACTION_TYPE_REJECT,
            "audit": ActionType.ACTION_TYPE_AUDIT,
            "ui_required": ActionType.ACTION_TYPE_UI_REQUIRED,
            "error": ActionType.ACTION_TYPE_ERROR,
        }
        return mapping.get(action.lower(), ActionType.ACTION_TYPE_UNSPECIFIED)

    def _status_to_enum(self, status: str) -> Status:
        """Convert status string to Status enum."""
        mapping: dict[str, Status] = {
            "ok": Status.STATUS_OK,
            "degraded": Status.STATUS_DEGRADED,
            "error": Status.STATUS_ERROR,
            "critical": Status.STATUS_CRITICAL,
        }
        return mapping.get(status.lower(), Status.STATUS_UNSPECIFIED)

    def _severity_to_enum(self, severity: str) -> Severity:
        """Convert severity string to Severity enum."""
        mapping: dict[str, Severity] = {
            "info": Severity.SEVERITY_INFO,
            "warning": Severity.SEVERITY_WARNING,
            "error": Severity.SEVERITY_ERROR,
            "critical": Severity.SEVERITY_CRITICAL,
        }
        return mapping.get(severity.lower(), Severity.SEVERITY_UNSPECIFIED)


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
            callback: Async function(event: Event) -> None
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
    ) -> list[Event]:
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
                    event = Event().parse(msg.data)
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
