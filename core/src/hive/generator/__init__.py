import uuid

import structlog

# from .main import HiveGenerator as HiveGenerator
from aura_core import Event, Generator, Observation, SkillRegistry

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveGenerator(Generator[Observation, Event]):
    """
    G - Generator: Emits binary proto events to NATS JetStream via Pulse Protein.

    Binary Bloodstream: All events are serialized as protobuf, not JSON.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry
        self.settings = get_settings()
        self._instance_id = uuid.uuid4().hex[:8]

    async def pulse(self, observation: Observation) -> list[Event]:
        """
        Generate binary proto events based on the observation.

        Flow: Observation -> Proto Event -> .SerializeToString() -> JetStream.publish()
        """
        # Extract trace context from observation metadata for OTel propagation
        trace_id = (
            observation.metadata.get("trace_id") if observation.metadata else None
        )
        span_id = observation.metadata.get("span_id") if observation.metadata else None

        # 1. Negotiation Event (binary proto)
        if observation.event_type and observation.event_type.startswith("negotiation_"):
            action = observation.event_type.replace("negotiation_", "")

            # Extract negotiation data from observation
            session_token = ""  # nosec B105
            price = 0.0
            item_id = ""
            agent_did = ""

            if hasattr(observation.data, "session_token"):
                session_token = observation.data.session_token
            if observation.metadata:
                decision = observation.metadata.get("decision")
                if decision:
                    price = getattr(decision, "price", 0.0)
                item_id = observation.metadata.get("item_id", "")
                agent_did = observation.metadata.get("agent_did", "")

            # Emit binary negotiation event via Pulse Protein
            await self.registry.execute(
                "pulse",
                "emit_negotiation",
                {
                    "session_token": session_token,
                    "action": action,
                    "price": price,
                    "item_id": item_id,
                    "agent_did": agent_did,
                    "trace_id": trace_id,
                    "span_id": span_id,
                },
            )

        # 2. System Heartbeat (binary proto)
        await self.registry.execute(
            "pulse",
            "emit_heartbeat",
            {
                "service": "core",
                "instance_id": self._instance_id,
                "status": "ok",
                "trace_id": trace_id,
                "span_id": span_id,
            },
        )
        return []

    async def emit_vitals(
        self, cpu_usage: float, memory_usage: float, status: str = "ok"
    ) -> bool:
        """Emit system vitals as binary proto event."""
        obs = await self.registry.execute(
            "pulse",
            "emit_vitals",
            {
                "service": "core",
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "status": status,
            },
        )
        return bool(obs.success)

    async def emit_alert(
        self, severity: str, message: str, source: str = "core"
    ) -> bool:
        """Emit an alert as binary proto event."""
        obs = await self.registry.execute(
            "pulse",
            "emit_alert",
            {
                "severity": severity,
                "message": message,
                "source": source,
            },
        )
        return bool(obs.success)
