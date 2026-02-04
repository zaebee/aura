import json
import logging
import time
from typing import Any

import nats
import nats.errors
from aura_core import Observation, SkillProtocol

from config import get_settings

logger = logging.getLogger(__name__)

class PulseSkill(SkillProtocol[dict[str, Any], Observation]):
    """
    Pulse Protein: Handles NATS event emission and heartbeats.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.nc = None

    def get_name(self) -> str:
        return "pulse"

    def get_capabilities(self) -> list[str]:
        return ["emit_event", "emit_heartbeat"]

    async def initialize(self) -> bool:
        try:
            self.nc = await nats.connect(self.settings.server.nats_url)
            logger.info(f"PulseSkill connected to NATS at {self.settings.server.nats_url}")
            return True
        except Exception as e:
            logger.warning(f"PulseSkill failed to connect to NATS: {e}")
            return False

    async def execute(self, intent: str, params: dict[str, Any]) -> Observation:
        if intent == "emit_event":
            return await self._emit_event(params.get("topic"), params.get("payload"))
        elif intent == "emit_heartbeat":
            return await self._emit_heartbeat()

        return Observation(success=False, error=f"Unknown intent: {intent}")

    async def _emit_event(self, topic: str | None, payload: dict | None) -> Observation:
        if not topic or payload is None:
            return Observation(success=False, error="topic and payload are required")

        if self.nc and self.nc.is_connected:
            try:
                await self.nc.publish(topic, json.dumps(payload).encode())
                return Observation(success=True)
            except Exception as e:
                return Observation(success=False, error=str(e))
        return Observation(success=False, error="NATS not connected")

    async def _emit_heartbeat(self) -> Observation:
        topic = "aura.hive.heartbeat"
        payload = {
            "status": "active",
            "timestamp": time.time(),
            "service": "core",
        }
        return await self._emit_event(topic, payload)

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()
