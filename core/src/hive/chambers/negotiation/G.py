import structlog
from aura_core import Observation

logger = structlog.get_logger(__name__)

async def emit_nats_event(obs: Observation):
    """The Pulse: Binary Protobuf pulse simulation."""
    logger.info("chamber_nats_emit", event_name=obs.event_type)

async def record_metrics(obs: Observation):
    """The Pulse: Prometheus increment simulation."""
    logger.info("chamber_metrics_record", success=obs.success)

async def pulse(obs: Observation):
    """The Echo: Internal reporting."""
    await emit_nats_event(obs)
    await record_metrics(obs)
