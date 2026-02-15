import uuid
from typing import Any

import betterproto
import structlog
from aura_core import Generator, SkillRegistry
from aura_core_gen.aura.core.v1 import Observation

from config import get_settings

logger = structlog.get_logger(__name__)


class HiveGenerator(Generator[Observation, Any]):
    """
    G - Generator: Emits binary proto events to NATS JetStream via Pulse Protein.
    Aligned with Chromosomal DNA v0.3.0.
    """

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.registry = registry
        self.settings = settings or get_settings()
        self._instance_id = uuid.uuid4().hex[:8]

    async def pulse(self, observation: Observation) -> list[Any]:
        """
        Generate binary proto events based on the observation.
        Flow: Observation -> Pulse Protein -> JetStream.
        """
        # 1. Negotiation Event
        if observation.event_type and observation.event_type.startswith("negotiation_"):
            action = observation.event_type.replace("negotiation_", "")

            # Extract negotiation data from observation
            price = 0.0
            item_id = ""
            agent_did = ""
            payment_uri = ""

            if observation.negotiation:
                neg = observation.negotiation
                item_id = neg.item_identifier
                payment_uri = neg.payment_uri

                # Extract price from oneof result
                res_name, res_val = betterproto.which_one_of(neg, "result")
                if res_name == "accepted" and res_val:
                    price = getattr(res_val, "final_price", 0.0)
                elif res_name == "countered" and res_val:
                    price = getattr(res_val, "proposed_price", 0.0)

            if observation.metadata:
                agent_did = str(observation.metadata.to_dict().get("agent_did", ""))

            # Emit binary negotiation event via Pulse Protein
            await self.registry.execute(
                "pulse",
                "emit_negotiation",
                {
                    "action": action,
                    "price": price,
                    "item_id": item_id,
                    "agent_did": agent_did,
                    "payment_uri": payment_uri,
                    # Trace context should be handled by the trace field in Proto
                    "trace": observation.trace,
                },
            )

        # 2. System Heartbeat
        await self.registry.execute(
            "pulse",
            "emit_heartbeat",
            {
                "service": "core",
                "instance_id": self._instance_id,
                "status": "ok",
                "trace": observation.trace,
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
