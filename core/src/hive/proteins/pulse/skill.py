from typing import Any

from aura_core import Observation, SkillProtocol

from config.server import ServerSettings

from .engine import JetStreamProvider
from .schema import EventParams, NegotiationEventParams


class PulseSkill(
    SkillProtocol[ServerSettings, JetStreamProvider, dict[str, Any], Observation]
):
    """
    Pulse Protein: Handles NATS JetStream event emission with binary proto.
    """

    def __init__(self) -> None:
        self.settings: ServerSettings | None = None
        self.provider: JetStreamProvider | None = None
        self._capabilities = {
            "emit_heartbeat": self._emit_heartbeat,
            "emit_negotiation": self._emit_negotiation,
            "emit_vitals": self._emit_vitals,
            "emit_alert": self._emit_alert,
            "emit_audit": self._emit_audit,
            "emit_event": self._emit_event,
        }

    def get_name(self) -> str:
        return "pulse"

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities.keys())

    def bind(self, settings: ServerSettings, provider: JetStreamProvider) -> None:
        self.settings = settings
        self.provider = provider

    async def initialize(self) -> bool:
        if not self.provider:
            return False
        return await self.provider.connect()

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")

        handler = self._capabilities.get(intent)
        if not handler:
            return Observation(success=False, error=f"Unknown intent: {intent}")

        try:
            return await handler(params)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def _emit_heartbeat(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        success = await self.provider.publish_heartbeat(
            service=params.get("service", "core"),
            instance_id=params.get("instance_id"),
            status=params.get("status", "ok"),
            trace_id=params.get("trace_id"),
            span_id=params.get("span_id"),
        )
        return Observation(success=success, event_type="heartbeat")

    async def _emit_negotiation(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        p = NegotiationEventParams(**params)
        success = await self.provider.publish_negotiation_event(
            session_token=p.session_token,
            action=p.action,
            price=p.price,
            item_id=p.item_id,
            agent_did=p.agent_did,
            trace_id=params.get("trace_id"),
            span_id=params.get("span_id"),
        )
        return Observation(success=success, event_type=f"negotiation_{p.action}")

    async def _emit_vitals(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        success = await self.provider.publish_vitals(
            service=params.get("service", "core"),
            cpu_usage=params.get("cpu_usage", 0.0),
            memory_usage=params.get("memory_usage", 0.0),
            status=params.get("status", "ok"),
            trace_id=params.get("trace_id"),
            span_id=params.get("span_id"),
        )
        return Observation(success=success, event_type="vitals")

    async def _emit_alert(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        success = await self.provider.publish_alert(
            severity=params.get("severity", "info"),
            message=params.get("message", ""),
            source=params.get("source", "unknown"),
            trace_id=params.get("trace_id"),
            span_id=params.get("span_id"),
        )
        return Observation(success=success, event_type="alert")

    async def _emit_audit(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        success = await self.provider.publish_audit(
            repo_name=params.get("repo_name", ""),
            is_pure=params.get("is_pure", False),
            heresies=params.get("heresies", []),
            negotiation_success_rate=params.get("negotiation_success_rate", 0.0),
            trace_id=params.get("trace_id"),
            span_id=params.get("span_id"),
        )
        return Observation(success=success, event_type="audit")

    async def _emit_event(self, params: dict[str, Any]) -> Observation:
        assert self.provider is not None
        # Deprecated: fallback to raw JSON publish
        event_params = EventParams(**params)
        success = await self.provider.publish_raw(
            event_params.topic, event_params.payload
        )
        return Observation(success=success, event_type="raw")

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
