from typing import Any

from aura_core import (
    Membrane,
    SkillRegistry,
)
from aura_core_gen.aura.core.v1 import (
    Context,
    Intent,
)

from aura_hive.config import get_settings

from .inbound import InboundScreening
from .outbound import OutboundPipeline
from .verdict import _Verdict


class HiveMembrane(Membrane[Any, Intent, Context]):
    """The Immune System: Deterministic Guardrails using Guard Protein."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.settings = get_settings()
        self.registry = registry
        self.inbound = InboundScreening()
        self.outbound = OutboundPipeline(registry, self.settings)

    async def inspect_inbound(self, signal: Any) -> Any:
        return await self.inbound.check(signal)

    async def inspect_outbound(self, decision: Intent, context: Context) -> Intent:
        # Accumulated as the path proceeds and minted once, at whichever return
        # is taken.
        verdict = _Verdict()
        return await self.outbound.run(decision, context, verdict)
