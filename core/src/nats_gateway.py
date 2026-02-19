"""
NATS Signal Gateway — receives signals from synapses and feeds them into MetabolicLoop.

This is the core-side counterpart of the synapse NATS adapters.
Synapses publish Signal protos to their signal subjects; this gateway subscribes,
runs the MetabolicLoop, and replies with Observation protos.

Channels:
- Inbound:  aura.synapse.*.signal  (signals from synapses)
- Outbound: NATS reply inbox        (observation back to synapse)
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import nats
import nats.errors
import structlog
from aura_core_gen.aura.core.v1 import Observation, Signal

if TYPE_CHECKING:
    from nats.aio.msg import Msg

logger = structlog.get_logger("nats_gateway")


class EvolutionaryEvent:
    """Track mutation attempts for BeeKeeper analysis"""

    def __init__(
        self, original_error: str, mutation_attempts: list[str], success: bool
    ):
        self.original_error = original_error
        self.mutation_attempts = mutation_attempts
        self.success = success
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "original_error": self.original_error,
            "mutation_attempts": self.mutation_attempts,
            "success": self.success,
            "timestamp": self.timestamp,
        }


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
        """Handle an incoming signal from a synapse with somatic hypermutation."""
        evolutionary_event = None

        try:
            logger.debug(
                "gateway_received_signal",
                subject=msg.subject,
                size=len(msg.data),
            )

            # 1. Feed raw signal bytes into MetabolicLoop
            try:
                observation = await self.metabolism.execute(msg.data, is_nats=True)
            except Exception as e:
                # Somatic Hypermutation: Attempt to heal the signal
                logger.warning(
                    "signal_parse_error_triggering_mutation",
                    error=str(e),
                    subject=msg.subject,
                )
                observation = await self._attempt_signal_mutation(msg.data, str(e))
                evolutionary_event = EvolutionaryEvent(
                    str(e),
                    ["initial_parse_failed", "mutation_attempted"],
                    observation.success,
                )

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

        # Log evolutionary event for BeeKeeper analysis
        if evolutionary_event:
            logger.info(
                "evolutionary_event_recorded", event=evolutionary_event.to_dict()
            )
            # In a real implementation, this would be sent to BeeKeeper for analysis

    async def _attempt_signal_mutation(
        self, signal_data: bytes, original_error: str
    ) -> Observation:
        """Attempt to heal malformed signals through mutation strategies"""
        mutation_attempts = []

        strategies = [
            self._try_utf8_fallback,
            self._try_json_parsing,
            self._try_raw_text_wrapping,
            self._try_proto_field_stripping,
        ]

        for strategy in strategies:
            try:
                mutation_attempts.append(strategy.__name__)
                result = await strategy(signal_data, original_error)
                if result.success:
                    logger.debug(
                        "mutation_strategy_succeeded",
                        strategy=strategy.__name__,
                        attempts=len(mutation_attempts),
                    )
                    return result
            except Exception as e:
                mutation_attempts.append(f"{strategy.__name__}_failed: {str(e)}")
                continue

        # All strategies failed
        return Observation(
            success=False,
            error=f"All mutation strategies failed. Original: {original_error}",
            event_type="mutation_failure",
        )

    async def _try_utf8_fallback(
        self, signal_data: bytes, original_error: str
    ) -> Observation:
        """Try to decode as UTF-8 and re-encode"""
        try:
            text = signal_data.decode("utf-8")
            # Try to parse as JSON first
            try:
                json_data = json.loads(text)
                if "signal" in json_data:
                    # Wrap in proper Signal structure
                    signal = Signal()
                    signal.signal_id = json_data.get("signal_id", "json_signal")
                    if "negotiation" in json_data:
                        from aura_core_gen.aura.core.v1 import NegotiationSignal

                        negotiation_data = json_data["negotiation"]
                        signal.negotiation = NegotiationSignal(
                            item_identifier=negotiation_data.get(
                                "item_identifier", "unknown"
                            ),
                            item_domain=negotiation_data.get("item_domain", "unknown"),
                            bid_amount=float(negotiation_data.get("bid_amount", 0.0)),
                        )
                    return cast(
                        Observation,
                        await self.metabolism.execute(signal, is_nats=False),
                    )
            except json.JSONDecodeError:
                pass

            # Fallback: treat as raw text signal
            signal = Signal()
            signal.signal_id = "mutated_" + str(hash(text))
            # Create a minimal negotiation signal
            from aura_core_gen.aura.core.v1 import NegotiationSignal

            signal.negotiation = NegotiationSignal(
                item_identifier=text[:100]
            )  # Truncate if too long
            return cast(
                Observation, await self.metabolism.execute(signal, is_nats=False)
            )

        except Exception as e:
            raise ValueError(f"UTF-8 mutation failed: {e}") from e

    async def _try_json_parsing(
        self, signal_data: bytes, original_error: str
    ) -> Observation:
        """Try to parse as JSON and convert to proto"""
        try:
            text = signal_data.decode("utf-8", errors="replace")
            json_data = json.loads(text)

            # Convert JSON to Signal proto
            signal = Signal()
            signal.signal_id = json_data.get("signal_id", "mutated_json")

            # Handle different signal types
            if "negotiation" in json_data:
                from aura_core_gen.aura.core.v1 import NegotiationSignal

                negotiation_data = json_data["negotiation"]
                signal.negotiation = NegotiationSignal(
                    item_identifier=negotiation_data.get("item_identifier", "unknown"),
                    item_domain=negotiation_data.get("item_domain", "unknown"),
                    bid_amount=float(negotiation_data.get("bid_amount", 0.0)),
                )

            return cast(
                Observation, await self.metabolism.execute(signal, is_nats=False)
            )

        except Exception as e:
            raise ValueError(f"JSON mutation failed: {e}") from e

    async def _try_raw_text_wrapping(
        self, signal_data: bytes, original_error: str
    ) -> Observation:
        """Wrap raw text in a minimal signal structure"""
        try:
            text = signal_data.decode("utf-8", errors="replace")

            # Create minimal signal with text as item identifier
            from aura_core_gen.aura.core.v1 import NegotiationSignal

            signal = Signal()
            signal.signal_id = f"text_wrapped_{hash(text)}"
            signal.negotiation = NegotiationSignal(
                item_identifier=text[:255],  # Limit length
                item_domain="raw_text",
                bid_amount=0.0,
            )

            return cast(
                Observation, await self.metabolism.execute(signal, is_nats=False)
            )

        except Exception as e:
            raise ValueError(f"Raw text wrapping failed: {e}") from e

    async def _try_proto_field_stripping(
        self, signal_data: bytes, original_error: str
    ) -> Observation:
        """Try to parse proto but strip problematic fields"""
        try:
            # Try to parse the original signal but catch field errors
            signal = Signal()

            # Try partial parsing by reading raw bytes
            try:
                # betterproto uses parse() instead of ParseFromString
                signal.parse(signal_data)
                return cast(
                    Observation, await self.metabolism.execute(signal, is_nats=False)
                )
            except Exception:
                # If parsing fails, try to create minimal signal
                signal.signal_id = f"stripped_{hash(signal_data)}"
                from aura_core_gen.aura.core.v1 import NegotiationSignal

                signal.negotiation = NegotiationSignal(
                    item_identifier=f"recovered_{hash(signal_data)}",
                    item_domain="recovered",
                    bid_amount=0.0,
                )
                return cast(
                    Observation, await self.metabolism.execute(signal, is_nats=False)
                )

        except Exception as e:
            raise ValueError(f"Proto field stripping failed: {e}") from e

    async def stop(self) -> None:
        """Unsubscribe and close NATS connection."""
        if self._sub:
            await self._sub.unsubscribe()
        if self.nc:
            await self.nc.close()
            logger.info("nats_gateway_stopped")
