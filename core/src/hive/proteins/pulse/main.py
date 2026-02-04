import json
import time
from typing import Any

import nats
import nats.errors
from aura_core import Observation, SkillProtocol
from config import get_settings

class PulseSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Pulse Protein: Encapsulates NATS messaging and event emission.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.nc = None

    def get_name(self) -> str:
        return "pulse"

    def get_capabilities(self) -> list[str]:
        return ["emit_event", "initialize_nats"]

    async def initialize(self) -> bool:
        try:
            self.nc = await nats.connect(self.settings.server.nats_url)
            return True
        except Exception:
            return False

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        match intent:
            case "emit_event":
                return await self._emit_event(params)

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def _emit_event(self, params: dict[str, Any]) -> Observation:
        if not self.nc or not self.nc.is_connected:
             return Observation(success=False, error="NATS not connected")

        topic = params.get("topic")
        payload = params.get("payload", {})

        try:
            await self.nc.publish(topic, json.dumps(payload).encode())
            return Observation(success=True)
        except Exception as e:
            return Observation(success=False, error=str(e))

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()
