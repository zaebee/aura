"""
NATS Adapter — bridge between Telegram synapse and Core via NATS queues.

Two channels:
- Outbound (to core): publishes Signal to signal_subject, receives Observation reply
- Inbound (from core): Effector subscribes to aura.hive.events.> for async events
"""

import nats
import nats.errors
import structlog
from aura_core.gen.aura.dna.v1 import Observation as ProtoObservation
from aura_core.gen.aura.dna.v1 import Signal

logger = structlog.get_logger(__name__)

# Default NATS subjects
SUBJECT_SIGNAL = "aura.synapse.telegram.signal"
SUBJECT_EVENTS = "aura.hive.events.>"


class NatsAdapter:
    """
    Adapter for communicating with Core via NATS request/reply.

    Replaces the in-process MetabolicLoop dependency.
    The bot publishes a binary Signal proto and waits for a binary Observation proto reply.
    """

    def __init__(
        self,
        nc: nats.NATS,
        signal_subject: str = SUBJECT_SIGNAL,
        timeout: float = 30.0,
    ):
        self.nc = nc
        self.signal_subject = signal_subject
        self.timeout = timeout

    async def execute(self, signal: Signal) -> ProtoObservation:
        """
        Send Signal to core and wait for Observation reply.

        Uses NATS request/reply pattern:
        - Publishes serialized Signal proto to the signal subject
        - Waits for core to reply with serialized Observation proto
        """
        try:
            signal_bytes = bytes(signal)
            logger.debug(
                "adapter_sending_signal",
                signal_id=signal.signal_id,
                signal_type=signal.signal_type,
                subject=self.signal_subject,
            )

            response = await self.nc.request(
                self.signal_subject,
                signal_bytes,
                timeout=self.timeout,
            )

            observation = ProtoObservation().parse(response.data)
            logger.debug(
                "adapter_received_observation",
                success=observation.success,
                event_type=observation.event_type,
            )
            return observation

        except nats.errors.NoRespondersError:
            logger.error("adapter_no_responders", subject=self.signal_subject)
            return ProtoObservation(
                success=False,
                error="Core service is not available (no responders)",
            )

        except nats.errors.TimeoutError:
            logger.error(
                "adapter_timeout",
                subject=self.signal_subject,
                timeout=self.timeout,
            )
            return ProtoObservation(
                success=False,
                error="Core service did not respond in time",
            )

        except Exception as e:
            logger.error("adapter_error", error=str(e))
            return ProtoObservation(
                success=False,
                error=f"Adapter communication error: {e}",
            )
