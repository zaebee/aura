"""
NATS Signal Gateway — receives signals from synapses and feeds them into MetabolicLoop.

This is the core-side counterpart of the synapse NATS adapters.
Synapses publish Signal protos to their signal subjects; this gateway subscribes,
runs the MetabolicLoop, and replies with Observation protos.

Channels:
- Inbound:  aura.synapse.*.signal  (signals from synapses)
- Outbound: NATS reply inbox        (observation back to synapse)
"""

from typing import TYPE_CHECKING, Any

import nats
import nats.errors
import structlog
from aura_core.gen.aura.core.v1 import Observation

if TYPE_CHECKING:
    from nats.aio.msg import Msg

logger = structlog.get_logger("nats_gateway")

# Queue group for load balancing across core instances
QUEUE_GROUP = "core-signal-processor"

# Default subject pattern — matches all synapse signal subjects
DEFAULT_SIGNAL_SUBJECT = "aura.synapse.*.signal"


class NatsSignalGateway:
    """
    Subscribes to synapse signal subjects via NATS.
    Feeds raw signal bytes into the MetabolicLoop and replies with Observations.

    Uses NATS queue groups so multiple core instances can share the load.
    """

    def __init__(
        self,
        nats_url: str,
        metabolism: Any,
        signal_subject: str = DEFAULT_SIGNAL_SUBJECT,
    ):
        self.nats_url = nats_url
        self.metabolism = metabolism
        self.signal_subject = signal_subject
        self.nc: nats.NATS | None = None
        self._sub: Any = None

    async def start(self) -> bool:
        """Connect to NATS and start subscribing to synapse signals."""
        try:
            self.nc = await nats.connect(
                self.nats_url,
                connect_timeout=5,
                reconnect_time_wait=2,
                max_reconnect_attempts=60,
            )
            self._sub = await self.nc.subscribe(
                self.signal_subject,
                queue=QUEUE_GROUP,
                cb=self._on_signal,
            )
            logger.info(
                "nats_gateway_started",
                subject=self.signal_subject,
                queue_group=QUEUE_GROUP,
            )
            return True
        except Exception as e:
            logger.error("nats_gateway_start_failed", error=e, exc_info=True)
            return False

    async def _on_signal(self, msg: "Msg") -> None:
        """Handle an incoming signal from a synapse."""
        try:
            logger.debug(
                "gateway_received_signal",
                subject=msg.subject,
                size=len(msg.data),
            )

            # 1. Feed raw signal bytes into MetabolicLoop
            #    The aggregator detects bytes and parses them as a proto Signal.
            observation = await self.metabolism.execute(msg.data, is_nats=True)

            # 2. Reply with serialized proto Observation
            if msg.reply:
                await msg.respond(bytes(observation))
                logger.debug(
                    "gateway_replied",
                    success=observation.success,
                    event_type=observation.event_type,
                )
            else:
                logger.debug(
                    "gateway_no_reply_inbox",
                    subject=msg.subject,
                )

        except Exception as e:
            logger.error(
                "gateway_signal_processing_failed",
                error=e,
                subject=msg.subject,
                exc_info=True,
            )
            # Try to reply with error observation so the synapse doesn't hang
            if msg.reply:
                error_obs = Observation(
                    success=False,
                    error=f"Signal processing failed: {e}",
                )
                try:
                    await msg.respond(bytes(error_obs))
                except Exception as reply_err:
                    logger.warning(
                        "failed_to_send_error_reply",
                        error=str(reply_err),
                    )

    async def stop(self) -> None:
        """Unsubscribe and close NATS connection."""
        if self._sub:
            await self._sub.unsubscribe()
        if self.nc:
            await self.nc.close()
            logger.info("nats_gateway_stopped")
