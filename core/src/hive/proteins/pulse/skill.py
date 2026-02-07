from typing import Any

from aura_core import Observation, SkillProtocol

from config.server import ServerSettings

from .broker import JetStreamProvider
from .schema import EventParams, NegotiationEventParams


class PulseSkill(SkillProtocol[ServerSettings, JetStreamProvider, dict[str, Any], Observation]):
    """
    Pulse Protein: Handles NATS JetStream event emission with binary proto.

    Binary Bloodstream: All events are serialized as protobuf, not JSON.
    """

    def __init__(self) -> None:
        self.settings: ServerSettings | None = None
        self.provider: JetStreamProvider | None = None

    def get_name(self) -> str:
        return "pulse"

    def get_capabilities(self) -> list[str]:
        return [
            "emit_event",           # Generic event (deprecated, use typed methods)
            "emit_heartbeat",       # Binary heartbeat
            "emit_negotiation",     # Binary negotiation event
            "emit_vitals",          # Binary vitals event
            "emit_alert",           # Binary alert event
            "emit_audit",           # Binary audit event
        ]

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

        try:
            match intent:
                case "emit_heartbeat":
                    success = await self.provider.publish_heartbeat(
                        service=params.get("service", "core"),
                        instance_id=params.get("instance_id"),
                        status=params.get("status", "ok"),
                        trace_id=params.get("trace_id"),
                        span_id=params.get("span_id"),
                    )
                    return Observation(success=success, event_type="heartbeat")

                case "emit_negotiation":
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

                case "emit_vitals":
                    success = await self.provider.publish_vitals(
                        service=params.get("service", "core"),
                        cpu_usage=params.get("cpu_usage", 0.0),
                        memory_usage=params.get("memory_usage", 0.0),
                        status=params.get("status", "ok"),
                        trace_id=params.get("trace_id"),
                        span_id=params.get("span_id"),
                    )
                    return Observation(success=success, event_type="vitals")

                case "emit_alert":
                    success = await self.provider.publish_alert(
                        severity=params.get("severity", "info"),
                        message=params.get("message", ""),
                        source=params.get("source", "unknown"),
                        trace_id=params.get("trace_id"),
                        span_id=params.get("span_id"),
                    )
                    return Observation(success=success, event_type="alert")

                case "emit_audit":
                    success = await self.provider.publish_audit(
                        repo_name=params.get("repo_name", ""),
                        is_pure=params.get("is_pure", False),
                        heresies=params.get("heresies", []),
                        negotiation_success_rate=params.get("negotiation_success_rate", 0.0),
                        trace_id=params.get("trace_id"),
                        span_id=params.get("span_id"),
                    )
                    return Observation(success=success, event_type="audit")

                case "emit_event":
                    # Deprecated: fallback to raw JSON publish
                    event_params = EventParams(**params)
                    success = await self.provider.publish_raw(event_params.topic, event_params.payload)
                    return Observation(success=success, event_type="raw")

                case _:
                    return Observation(success=False, error=f"Unknown intent: {intent}")

        except Exception as e:
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
