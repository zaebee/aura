from pathlib import Path
from typing import Any

import structlog
from aura_core import (
    Aggregator,
    HiveContext,
    SkillRegistry,
    SystemVitals,
    resolve_brain_path,
)
from aura_core.gen.aura.dna.v1 import ItemData, NegotiationOffer, Signal

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, HiveContext]):
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

        # DNA Rule: Relative path resolution for brain
        if not compiled_path:
            # Look in core/data relative to this file
            possible_path = Path(__file__).parents[3] / "data" / "aura_brain.json"
            if possible_path.exists():
                compiled_path = str(possible_path)

        self.brain_path = resolve_brain_path(compiled_path)

    async def get_vitals(self) -> SystemVitals:
        """Standardized proprioception (self-healing metrics) via Telemetry Protein."""
        try:
            # Call Telemetry Protein via SkillRegistry
            obs = await self.registry.execute("telemetry", "fetch_metrics", {})
            if obs.success and obs.system_vitals:
                return obs.system_vitals
            from aura_core.gen.aura.dna.v1 import VitalsStatus
            return SystemVitals(status=VitalsStatus.VITALS_STATUS_DEGRADED, error=obs.error or "unknown_error")
        except Exception as e:
            logger.error("aggregator_vitals_unexpected_error", error=str(e))
            return SystemVitals(status="error", timestamp="", error=str(e))

    async def get_system_metrics(self) -> dict[str, Any]:
        """Backward compatibility for legacy status calls."""
        import betterproto
        vitals = await self.get_vitals()
        # Betterproto to_dict() works well for compatibility
        return vitals.to_dict(casing=betterproto.Casing.SNAKE, include_default_values=True)

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

        item_data = ItemData()
        try:
            # Call Persistence Protein via SkillRegistry
            obs = await self.registry.execute(
                "persistence", "read_item", {"item_id": item_id}
            )
            if obs.success and obs.item:
                item_data = obs.item
        except Exception as e:
            logger.error("aggregator_persistence_error", error=str(e))

        return HiveContext(
            item_id=item_id,
            offer=offer,
            item=item_data,
            # system_health will be automatically injected by MetabolicLoop
            request_id=request_id,
            metadata={"brain_path": self.brain_path},
        )
