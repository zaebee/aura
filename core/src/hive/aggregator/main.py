from typing import Any

import structlog
from aura_core import (
    Aggregator,
    HiveContext,
    NegotiationOffer,
    SkillRegistry,
    SystemVitals,
    resolve_brain_path,
)
from aura_core.gen.aura.dna.v1 import Signal

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, HiveContext]):
    """A - Aggregator: Consolidates persistence and telemetry signals."""

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.settings = settings
        self.registry = registry
        compiled_path = None
        if settings and hasattr(settings, "llm") and hasattr(settings.llm, "compiled_program_path"):
            compiled_path = settings.llm.compiled_program_path
        self.brain_path = resolve_brain_path(compiled_path)

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics) via Telemetry Protein."""
        try:
            # Call Telemetry Protein via SkillRegistry
            obs = await self.registry.execute("telemetry", "fetch_metrics", {})
            if obs.success:
                return SystemVitals(**obs.data)
            return SystemVitals(status="unstable", timestamp="", error=obs.error)
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))
            return SystemVitals(status="error", timestamp="", error=str(e))

    async def get_system_metrics(self) -> dict[str, Any]:
        """Backward compatibility for legacy status calls."""
        vitals = await self.get_vitals()
        return dict(vitals.model_dump())

    async def perceive(self, signal: Any, **kwargs: Any) -> HiveContext:
        """
        Perceive signal and turn it into Context.
        Supports both gRPC objects and binary Proto signals.
        """
        # Handle binary proto signal (Binary Bloodstream)
        if isinstance(signal, bytes):
            try:
                proto_signal = Signal().parse(signal)
                if proto_signal.negotiation:
                    item_id = proto_signal.negotiation.item_id
                    request_id = proto_signal.signal_id
                    offer = NegotiationOffer(
                        bid_amount=proto_signal.negotiation.bid_amount,
                        reputation=proto_signal.negotiation.agent.reputation_score,
                        agent_did=proto_signal.negotiation.agent.did,
                    )
                else:
                    raise ValueError("Signal does not contain negotiation payload")
            except Exception as e:
                logger.error("binary_signal_decode_failed", error=str(e))
                raise ValueError(f"Failed to decode binary signal: {e}") from e
        else:
            # Handle gRPC request object
            item_id = signal.item_id
            request_id = getattr(signal, "request_id", "")
            offer = NegotiationOffer(
                bid_amount=signal.bid_amount,
                reputation=signal.agent.reputation_score,
                agent_did=signal.agent.did,
            )

        item_data = {}
        try:
            # Call Persistence Protein via SkillRegistry
            obs = await self.registry.execute(
                "persistence", "read_item", {"item_id": item_id}
            )
            if obs.success and obs.data:
                item = obs.data
                item_data = {
                    "id": item["id"],
                    "name": item["name"],
                    "base_price": item["base_price"],
                    "floor_price": item["floor_price"],
                    "meta": item["meta"] or {},
                }
        except Exception as e:
            logger.error("aggregator_persistence_error", error=str(e))

        # Fetch vitals (Proprioception)
        system_health = await self.get_vitals()

        return HiveContext(
            item_id=item_id,
            offer=offer,
            item_data=item_data,
            system_health=system_health,
            request_id=request_id,
            metadata={"brain_path": self.brain_path},
        )
