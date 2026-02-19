"""
Pulse Protein Internal - NATS JetStream Provider for Binary Bloodstream.

Handles binary proto serialization and JetStream publishing using chromosomal DNA.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import nats
import nats.errors
from aura_core import make_struct
from aura_core_gen.aura.core.v1 import (
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
    Uses betterproto chromosomal signals.
    """

    def __init__(self, nats_url: str, signer: AuditSigner | None = None):
        self.nats_url = nats_url
        self._signer = signer
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

    def _create_trace_context(
        self, trace_id: str | None = None, span_id: str | None = None
    ) -> TraceContext:
        """Create trace context for OTel propagation."""
        return TraceContext(
            trace_id=trace_id or uuid.uuid4().hex,
            span_id=span_id or uuid.uuid4().hex[:16],
            trace_flags="01",
        )

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
            return False

        try:
            event = Event(
                identifier=f"neg-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.events.negotiation_{action}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                negotiation=NegotiationEvent(
                    item_identifier=item_id,
                    action=self._action_to_enum(action),
                    price=price,
                ),
                metadata=make_struct(
                    {
                        "session_token": session_token,
                        "agent_did": agent_did,
                    }
                ),
            )

            binary_data = bytes(event)
            ack = await self.js.publish(event.topic, binary_data)
            logger.debug(f"Published negotiation event: seq={ack.seq}")
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
            return False

        try:
            event = Event(
                identifier=f"hb-{uuid.uuid4().hex[:8]}",
                topic="aura.hive.heartbeat",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                heartbeat=HeartbeatEvent(
                    service=service,
                    instance_id=instance_id or uuid.uuid4().hex[:8],
                    status=self._status_to_enum(status),
                ),
            )

            binary_data = bytes(event)
            headers: dict[str, str] | None = None
            if self._signer:
                try:
                    ts = datetime.now(UTC).isoformat()
                    headers = self._signer.make_headers(event.topic, binary_data, ts)
                except Exception:
                    logger.warning("aromatic_seal_failed", exc_info=True)
            ack = await self.js.publish(event.topic, binary_data, headers=headers)
            logger.debug(f"Published heartbeat: seq={ack.seq}")
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
            event = Event(
                identifier=f"vit-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.vitals.{service}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                vitals=VitalsEvent(
                    service=service,
                    status=self._status_to_enum(status),
                    cpu_usage_percent=cpu_usage,
                    memory_usage_mb=memory_usage,
                ),
            )

            binary_data = bytes(event)
            ack = await self.js.publish(event.topic, binary_data)
            logger.debug(f"Published vitals: seq={ack.seq}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish vitals: {e}")
            return False

    async def publish_alert(
        self,
        severity_str: str,
        message: str,
        source: str,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> bool:
        """Publish an alert event as binary proto."""
        if not self.js:
            return False

        try:
            event = Event(
                identifier=f"alert-{uuid.uuid4().hex[:8]}",
                topic=f"aura.hive.events.alert_{severity_str}",
                timestamp=datetime.now(UTC),
                trace=self._create_trace_context(trace_id, span_id),
                alert=AlertEvent(
                    severity=self._severity_to_enum(severity_str),
                    message=message,
                    source=source,
                ),
            )

            binary_data = bytes(event)
            ack = await self.js.publish(event.topic, binary_data)
            logger.debug(f"Published alert: seq={ack.seq}")

            # Duplicate to error topic if severity is high
            if event.alert.severity in [
                Severity.SEVERITY_ERROR,
                Severity.SEVERITY_CRITICAL,
            ]:
                error_topic = "aura.hive.events.error"
                await self.js.publish(error_topic, binary_data)
                logger.debug(f"Duplicated error alert to {error_topic}")

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
        """Publish an alert event as binary proto."""
        if not self.js:
            return False

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
                    negotiation_success_rate=negotiation_success_rate,
                ),
            )

            binary_data = bytes(event)
            headers: dict[str, str] | None = None
            if self._signer:
                try:
                    ts = datetime.now(UTC).isoformat()
                    headers = self._signer.make_headers(event.topic, binary_data, ts)
                except Exception:
                    logger.warning("aromatic_seal_failed", exc_info=True)
            ack = await self.js.publish(event.topic, binary_data, headers=headers)
            logger.debug(f"Published audit: seq={ack.seq}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish audit: {e}")
            return False

    async def publish_raw(self, topic: str, payload: dict[str, Any]) -> bool:
        """Fallback: Publish raw event (for backward compatibility)."""
        if not self.js:
            return False

        try:
            import json

            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            await self.js.publish(topic, data)
            logger.warning(f"Published raw JSON (deprecated): {topic}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish raw: {e}")
            return False

    async def close(self) -> None:
        """Close NATS connection."""
        if self.nc:
            await self.nc.close()

    def _action_to_enum(self, action: str) -> ActionType:
        """Convert action string to ActionType enum."""
        mapping = {
            "accept": ActionType.ACTION_TYPE_ACCEPT,
            "counter": ActionType.ACTION_TYPE_COUNTER,
            "reject": ActionType.ACTION_TYPE_REJECT,
            "audit": ActionType.ACTION_TYPE_APPROVE,  # Map audit to approve for now
            "ui_required": ActionType.ACTION_TYPE_UPDATE,  # Map UI to update
            "error": ActionType.ACTION_TYPE_ERROR,
        }
        return cast(
            ActionType, mapping.get(action.lower(), ActionType.ACTION_TYPE_UNSPECIFIED)
        )

    def _status_to_enum(self, status: str) -> Status:
        """Convert status string to Status enum."""
        mapping = {
            "ok": Status.STATUS_OK,
            "degraded": Status.STATUS_DEGRADED,
            "unstable": Status.STATUS_DEGRADED,
            "error": Status.STATUS_ERROR,
            "critical": Status.STATUS_CRITICAL,
        }
        return cast(Status, mapping.get(status.lower(), Status.STATUS_UNSPECIFIED))

    def _severity_to_enum(self, severity_str: str) -> Severity:
        """Convert severity string to Severity enum."""
        mapping = {
            "info": Severity.SEVERITY_INFO,
            "warning": Severity.SEVERITY_WARNING,
            "error": Severity.SEVERITY_ERROR,
            "critical": Severity.SEVERITY_CRITICAL,
        }
        return cast(
            Severity, mapping.get(severity_str.lower(), Severity.SEVERITY_UNSPECIFIED)
        )


class JetStreamSubscriber:
    """
    JetStream subscriber for consuming binary proto messages.
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
            return True
        except Exception:
            return False

    async def subscribe(
        self,
        stream: str,
        consumer: str,
        callback: Any,
    ) -> bool:
        if not self.js:
            return False

        try:
            psub = await self.js.pull_subscribe(
                subject="",
                durable=consumer,
                stream=stream,
            )
            self._subscriptions[f"{stream}:{consumer}"] = psub
            return True
        except Exception:
            return False

    async def fetch_events(
        self,
        stream: str,
        consumer: str,
        batch: int = 10,
        timeout: float = 1.0,
    ) -> list[Event]:
        key = f"{stream}:{consumer}"
        psub = self._subscriptions.get(key)

        if not psub:
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
                    await msg.nak()

            return events
        except nats.errors.TimeoutError:
            return []
        except Exception:
            return []

    async def close(self) -> None:
        """Close all subscriptions and NATS connection."""
        for _key, psub in self._subscriptions.items():
            try:
                await psub.unsubscribe()
            except Exception:  # nosec
                pass
        self._subscriptions.clear()

        if self.nc:
            await self.nc.close()


# Backward compatibility alias
NatsProvider = JetStreamProvider
