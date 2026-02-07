import structlog

from translator import MCPTranslator

logger = structlog.get_logger(__name__)

class MCPEffector:
    async def emit(self, event_binary: bytes) -> None:
        """Processes a binary event from the NATS bloodstream."""
        try:
            event = MCPTranslator.from_proto_event(event_binary)
            logger.info("effector_received_event", topic=event.topic)
            # MCP usually doesn't push to the client spontaneously in the current model,
            # but we could implement SSE or similar if needed.
        except Exception as e:
            logger.error("effector_failed_to_process_event", error=str(e))
