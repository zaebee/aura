from pathlib import Path
from typing import Any

import structlog
from aura_core import (
    Aggregator,
    HiveContext,
    NegotiationOffer,
    SkillRegistry,
    SystemVitals,
)

logger = structlog.get_logger(__name__)


class HiveAggregator(Aggregator[Any, HiveContext]):
    """A - Aggregator: Consolidates persistence and telemetry signals."""

    def __init__(self, registry: SkillRegistry, settings: Any = None) -> None:
        self.settings = settings
        self.registry = registry

    def _resolve_brain_path(self) -> str:
        if not self.settings:
            return "UNKNOWN"

        search_paths = []
        if hasattr(self.settings.llm, "compiled_program_path"):
            search_paths.append(Path(self.settings.llm.compiled_program_path))
        search_paths.extend(
            [
                Path("/app/src/aura_brain.json"),
                Path("./src/aura_brain.json"),
                Path(__file__).parent.parent / "aura_brain.json",
            ]
        )
        for path in search_paths:
            try:
                if path.exists() and path.is_file():
                    return str(path.absolute())
            except OSError:
                continue
        return "UNKNOWN"

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

        return HiveContext(
            item_id=item_id,
            offer=offer,
            item_data=item_data,
            # system_health will be automatically injected by MetabolicLoop
            request_id=request_id,
            metadata={"brain_path": self._resolve_brain_path()},
        )
