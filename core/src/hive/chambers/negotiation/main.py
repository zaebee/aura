from typing import Any

import structlog
from aura_core import Observation, SkillRegistry

from . import A, C, G, M, T

logger = structlog.get_logger(__name__)


async def negotiation_loop(signal: Any, registry: SkillRegistry) -> Observation:
    """
    The Ribosomal Loop: A -> M -> T -> M -> C -> G
    This is the heart of the Negotiation Chamber, now hydrated with real Proteins.
    """
    logger.info("chamber_loop_started")

    # 1. Perception (Past) - Hydrated with Storage/Monitor Proteins
    context = await A.perceive(signal, registry)

    # 2. Inbound Defense (The Firmament)
    context = await M.filter_in(context)

    # 3. Consciousness (Present) - Hydrated with Reasoning Protein
    intent = await T.think(context, registry)

    # 4. Outbound Defense (The Firmament)
    action = await M.filter_out(intent, context)

    # 5. Motor Execution (Future) - Hydrated with Transaction/Storage Proteins
    obs = await C.act(action, registry, context=context)

    # 6. Pulse (Echo) - Pulse/Telemetry reporting
    await G.pulse(obs, registry)

    logger.info("chamber_loop_completed", success=obs.success)
    return obs
