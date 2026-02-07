from typing import Any

import nats
import structlog
from aura_core.gen.aura.dna.v1 import Event as ProtoEvent
from opentelemetry import trace

from translator import MCPTranslator

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class MCPEffector:
    """
    Effector: Handles the 'Synaptic Gap' from the Hive back to MCP.
    In MCP, this usually maps to background event propagation or notifications.
    """

    def __init__(
        self,
        nats_client: nats.NATS | None = None,
        translator: MCPTranslator | None = None,
    ):
        self.nc = nats_client
        self.translator = translator

    async def run(self) -> None:
        """Background worker for MCP-related events."""
        if not self.nc:
            logger.warning("mcp_effector_no_nats_client")
            return

        try:
            # Subscribe to all hive events
            sub = await self.nc.subscribe("aura.hive.events.>")
            logger.info("mcp_effector_subscribed", subject="aura.hive.events.>")

            async for msg in sub.messages:
                with tracer.start_as_current_span("mcp_effector_on_event") as span:
                    span.set_attribute("subject", msg.subject)
                    await self._process_event(msg)
        except Exception as e:
            logger.error("mcp_effector_run_error", error=str(e))
            raise

    async def _process_event(self, msg: Any) -> None:
        """Process a single NATS message."""
        try:
            # 1. Parse binary proto event
            proto_event = ProtoEvent().parse(msg.data)
            logger.debug("mcp_effector_received_event", topic=proto_event.topic)

            # 2. Translate/Notify (MCP is mostly pull, but we can log for visibility)
            if self.translator:
                # We log the event topic for now
                logger.info("mcp_bloodstream_event", topic=proto_event.topic)

        except Exception as e:
            logger.error(
                "mcp_effector_processing_failed", subject=msg.subject, error=str(e)
            )
