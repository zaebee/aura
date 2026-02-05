import time
from typing import Any

from aura_core import Observation, SkillProtocol

from config.server import ServerSettings

from ._internal import NatsProvider
from .schema import EventParams


class PulseSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Pulse Protein: Handles NATS event emission and heartbeats.
    Standardized following the Crystalline Protein Standard.
    """

    def __init__(self) -> None:
        self.settings: ServerSettings | None = None
        self.provider: NatsProvider | None = None

    def get_name(self) -> str:
        return "pulse"

    def get_capabilities(self) -> list[str]:
        return ["emit_event", "emit_heartbeat"]

    async def initialize(self, settings: ServerSettings | None = None) -> bool:
        self.settings = settings
        if not self.settings:
            return False
        self.provider = NatsProvider(self.settings.nats_url)
        return await self.provider.connect()

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if not self.provider:
            return Observation(success=False, error="provider_not_initialized")
        try:
            if intent == "emit_event":
                p = EventParams(**params)
                success = await self.provider.publish(p.topic, p.payload)
                return Observation(success=success)

            elif intent == "emit_heartbeat":
                payload = {
                    "status": "active",
                    "timestamp": time.time(),
                    "service": "core",
                }
                success = await self.provider.publish("aura.hive.heartbeat", payload)
                return Observation(success=success)

            return Observation(success=False, error=f"Unknown intent: {intent}")
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.provider:
            await self.provider.close()
