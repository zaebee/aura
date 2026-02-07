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
        Generate binary proto events based on the observation using Pattern Matching.

        Flow: Observation -> Pulse Protein -> Binary Proto -> JetStream
        """
        # Purified Pulse: No manual extraction of trace_id or session_token.
        # Use Python 3.10+ match for dispatching.

        match observation.event_type:
            case str(et) if et.startswith("negotiation_"):
                action = et.replace("negotiation_", "")

                # Map observation to Pulse params via holistic metadata spread
                await self.registry.execute(
                    "pulse",
                    "emit_negotiation",
                    {
                        "action": action,
                        "session_token": getattr(observation.data, "session_token", ""),
                        "price": getattr(observation.metadata.get("decision"), "price", 0.0)
                                if observation.metadata and observation.metadata.get("decision") else 0.0,
                        **(observation.metadata or {}),
                    },
                )

            case "vitals":
                # Handle vitals events if emitted via observation
                await self.registry.execute(
                    "pulse",
                    "emit_vitals",
                    {
                        "service": "core",
                        **(observation.data or {}),
                        **(observation.metadata or {}),
                    }
                )

        # System Heartbeat (Always emitted)
        await self.registry.execute(
            "pulse",
            "emit_heartbeat",
            {
                "service": "core",
                "instance_id": self._instance_id,
                "status": "ok",
                **(observation.metadata or {}),
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
