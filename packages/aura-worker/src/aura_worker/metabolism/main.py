import asyncio
import base64
import json
import logging
from typing import Any

from nats.aio.client import Client as NATS

logger = logging.getLogger(__name__)

# NATS Subject for Vision RPC
VISION_ANALYZE_SUBJECT = "aura.worker.v1.vision.analyze"


class MetabolicLoop:
    """
    Worker Metabolic Loop: Manages NATS connectivity and control signals.
    Acts as the proprioceptive layer for the remote worker.
    """

    def __init__(
        self,
        worker_name: str,
        nats_url: str = "nats://localhost:4222",
        node: Any | None = None,
    ):
        self.worker_name = worker_name
        self.nats_url = nats_url
        self.nc = NATS()
        self.node = node
        self._kill_callback = None

    async def start(self, kill_callback: Any | None = None) -> bool:
        """Connect to NATS and subscribe to command signals."""
        self._kill_callback = kill_callback
        try:
            # We use a short connect timeout to avoid hanging the UI
            await self.nc.connect(
                self.nats_url,
                connect_timeout=2,
                reconnect_time_wait=1,
                max_reconnect_attempts=60,
            )

            # Subscribe to kill signals from the Gardener
            # Subject: aura.worker.<worker_name>.commands
            subject = f"aura.worker.{self.worker_name}.commands"
            await self.nc.subscribe(subject, cb=self._handle_message)

            # Subscribe to Vision RPC requests
            # Subject: aura.worker.v1.vision.analyze
            # Queue group: vision_swarm
            await self.nc.subscribe(
                VISION_ANALYZE_SUBJECT,
                queue="vision_swarm",
                cb=self._handle_vision_request,
            )

            logger.info(f"MetabolicLoop subscribed to {subject} and vision swarm")
            return True
        except Exception:
            logger.warning("MetabolicLoop NATS connection pending.")
            return False

    async def stop(self) -> None:
        """Disconnect from NATS."""
        if self.nc.is_connected:
            await self.nc.drain()
            await self.nc.close()

    async def _handle_message(self, msg: Any) -> None:
        """Handle incoming command messages."""
        try:
            data = msg.data.decode().strip().lower()
            if data == "kill":
                logger.warning(
                    f"!!! RECEIVED KILL SIGNAL FROM NATS ({msg.subject}) !!!"
                )
                if self._kill_callback:
                    if asyncio.iscoroutinefunction(self._kill_callback):
                        await self._kill_callback()
                    else:
                        self._kill_callback()
        except Exception as e:
            logger.error(f"Error handling NATS message: {e}")

    async def _handle_vision_request(self, msg: Any) -> None:
        """Handle incoming Vision RPC requests."""
        try:
            payload = json.loads(msg.data.decode())
            # Support both single image (legacy) and multiple images
            images_b64 = payload.get("images", [])
            if not images_b64 and payload.get("image"):
                images_b64 = [payload.get("image")]

            prompt = payload.get("prompt", "Analyze this image.")

            if not images_b64:
                await msg.respond(json.dumps({"error": "No images provided"}).encode())
                return

            if not self.node:
                await msg.respond(json.dumps({"error": "Node not initialized"}).encode())
                return

            images_bytes = [base64.b64decode(img) for img in images_b64]
            result = await self.node.analyze_vision(images_bytes, prompt)

            await msg.respond(json.dumps(result).encode())

        except Exception as e:
            logger.error(f"Vision RPC handler error: {e}")
            try:
                await msg.respond(json.dumps({"error": str(e)}).encode())
            except Exception:  # nosec B110
                pass

    @property
    def is_connected(self) -> bool:
        return bool(self.nc.is_connected)
