import structlog
from aura_core import Observation, SkillRegistry, get_action_name

logger = structlog.get_logger(__name__)


async def emit_nats_event(obs: Observation, registry: SkillRegistry) -> None:
    """The Pulse: Binary Protobuf pulse using Pulse Protein."""
    if not obs.success:
        return

    logger.info("chamber_nats_emit", event_name=obs.event_type)

    # Hydrate Pulse Protein
    action_name = get_action_name(obs.metadata.get("action"))
    if not action_name or action_name == "unknown":
        action_name = obs.event_type.replace("negotiation_", "")

    await registry.execute(
        "pulse",
        "emit_negotiation",
        {
            "session_token": obs.metadata.get("session_token", "unknown-session"),
            "action": action_name,
            "price": obs.metadata.get("price", 0.0),
            "item_id": obs.metadata.get("item_id", "unknown-item"),
            "agent_did": obs.metadata.get("agent_did", "unknown-agent"),
        },
    )


async def record_metrics(obs: Observation, registry: SkillRegistry) -> None:
    """The Pulse: Prometheus increment using Telemetry Protein."""
    logger.info("chamber_metrics_record", success=obs.success)

    # Hydrate Telemetry Protein
    await registry.execute(
        "telemetry",
        "increment_counter",
        {
            "name": "negotiation_total",
            "labels": {"service": "core", "chamber": "negotiation"},
        },
    )

    if obs.success and "accepted" in obs.event_type:
        await registry.execute(
            "telemetry",
            "increment_counter",
            {
                "name": "negotiation_accepted_total",
                "labels": {"service": "core", "chamber": "negotiation"},
            },
        )


async def pulse(obs: Observation, registry: SkillRegistry) -> None:
    """The Echo: Internal reporting via Skills."""
    await emit_nats_event(obs, registry)
    await record_metrics(obs, registry)
