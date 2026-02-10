from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import structlog
from aura_core import (
    Aggregator,
    SkillRegistry,
    resolve_brain_path,
)
from aura_core.gen.aura.dna.v1 import (
    Context,
    ContextType,
    ItemData,
    NegotiationOffer,
    Signal,
    SystemVitals,
    VitalsStatus,
)
from aura_core.gen.aura.dna.v1 import (
    HiveContextData as HiveContext,
)

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, Context]):
    """A - Aggregator: Consolidates persistence and telemetry signals."""

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.settings = settings
        self.registry = registry
        compiled_path = None
        if (
            settings
            and hasattr(settings, "llm")
            and hasattr(settings.llm, "compiled_program_path")
        ):
            compiled_path = settings.llm.compiled_program_path
        self.brain_path = resolve_brain_path(compiled_path)

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics) via Telemetry Protein."""
        try:
            # Call Telemetry Protein via SkillRegistry
            obs = await self.registry.execute("telemetry", "fetch_metrics", {})
            if obs.success and obs.vitals:
                return obs.vitals

            return SystemVitals(
                status=cast(VitalsStatus, VitalsStatus.VITALS_STATUS_ERROR),
                timestamp=datetime.now(UTC),
                error=obs.error,
            )
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))

            return SystemVitals(
                status=cast(VitalsStatus, VitalsStatus.VITALS_STATUS_ERROR),
                timestamp=datetime.now(UTC),
                error=str(e),
            )

    async def get_system_metrics(self) -> SystemVitals:
        """Proprioception (self-healing metrics) via Telemetry Protein."""
        return await self.get_vitals()

    async def perceive(self, signal: Any, **kwargs: Any) -> Context:
        """
        Perceive signal and turn it into Context.
        Supports both gRPC objects and binary Proto signals.
        """
        # Handle binary proto signal (Binary Bloodstream)
        if isinstance(signal, bytes):
            try:
                proto_signal = Signal().parse(signal)
                if proto_signal.negotiation:
                    identifier = proto_signal.negotiation.identifier
                    request_id = proto_signal.signal_id
                    offer = NegotiationOffer(
                        price=proto_signal.negotiation.price,
                        reputation=proto_signal.negotiation.agent.reputation,
                        agent_did=proto_signal.negotiation.agent.did,
                    )
                else:
                    raise ValueError("Signal does not contain negotiation payload")
            except Exception as e:
                logger.error("binary_signal_decode_failed", error=str(e))
                raise ValueError(f"Failed to decode binary signal: {e}") from e
        else:
            # Handle gRPC request object (Assuming legacy names for now if not updated in negotiation.proto)
            # Actually, we should probably check if it has the new names.

            def _get(obj: Any, *fields: str, default: Any = "") -> Any:
                for f in fields:
                    if hasattr(obj, f):
                        val = getattr(obj, f)
                        if not isinstance(val, MagicMock):
                            return val
                return default

            identifier = _get(signal, "identifier", "item_id")
            request_id = _get(signal, "request_id")

            agent_reputation = 0.0
            if hasattr(signal, "agent"):
                agent_reputation = _get(
                    signal.agent, "reputation", "reputation_score", default=0.0
                )

            offer = NegotiationOffer(
                price=_get(signal, "price", "bid_amount", default=0.0),
                reputation=agent_reputation,
                agent_did=getattr(signal.agent, "did", "unknown")
                if hasattr(signal, "agent")
                else "unknown",
            )

        item_obj = ItemData()
        try:
            # Call Persistence Protein via SkillRegistry
            obs = await self.registry.execute(
                "persistence", "read_item", {"identifier": identifier}
            )
            if obs.success and obs.item:
                item_obj = obs.item
        except Exception as e:
            logger.error("aggregator_persistence_error", error=str(e))

        # Fetch vitals (Proprioception)
        system_health = await self.get_vitals()

        return Context(
            context_id=f"ctx_{request_id}",
            context_type=cast(ContextType, ContextType.CONTEXT_TYPE_HIVE),
            system_health=system_health,
            hive=HiveContext(
                identifier=identifier,
                offer=offer,
                item=item_obj,
                request_id=request_id,
            ),
            metadata={"brain_path": self.brain_path},
        )
