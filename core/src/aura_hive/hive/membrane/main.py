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
from .metrics import _get_counter, _record_intervention, membrane_interventions_total
from .outbound import OutboundPipeline, logger
from .shaping import (
    _action_label,
    _as_dict,
    _context_number,
    _mint_for,
    _neutral_price_message,
    _quoted_price,
    _rejection,
    _replacing,
)
from .verdict import _EMIT, _OVERRIDE, _REFUSE, _UNAVAILABLE, _Verdict

# Re-exports: moved to verdict.py / shaping.py / metrics.py verbatim, still
# imported here so existing importers (tests import privates from this module)
# survive. Listed in __all__ so ruff reads the otherwise-unused ones as
# intentionally re-exported rather than dead imports. `logger` is the outbound
# module's own logger re-exported under this name, so the receipt-log tests
# that patch `membrane.main.logger` keep patching the object the moved code
# actually logs through.
__all__ = [
    "HiveMembrane",
    "_EMIT",
    "_OVERRIDE",
    "_REFUSE",
    "_UNAVAILABLE",
    "_Verdict",
    "_action_label",
    "_as_dict",
    "_context_number",
    "_get_counter",
    "_mint_for",
    "_neutral_price_message",
    "_quoted_price",
    "_record_intervention",
    "_rejection",
    "_replacing",
    "logger",
    "membrane_interventions_total",
]


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
