import json
import logging
from typing import Any

import nats
import nats.errors

logger = logging.getLogger(__name__)


class NatsProvider:
    def __init__(self, nats_url: str):
        self.nats_url = nats_url
        self.nc = None

    async def connect(self) -> bool:
        try:
            self.nc = await nats.connect(self.nats_url)  # type: ignore
            return True
        except Exception as e:
            logger.warning(f"NATS connection failed: {e}")
            return False

    async def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        if self.nc and self.nc.is_connected:
            await self.nc.publish(topic, json.dumps(payload).encode())
            return True
        return False

    async def close(self) -> None:
        if self.nc:
            await self.nc.close()
