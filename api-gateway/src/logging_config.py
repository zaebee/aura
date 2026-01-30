from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog
from opentelemetry.trace import get_current_span

# Context variable to store request_id across async boundaries
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def configure_logging() -> None:
    """Configure structlog to output JSON format for structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_otel_context,  # Add OpenTelemetry context to logs
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def add_otel_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Add OpenTelemetry context to log records."""
    try:
        span = get_current_span()
        if span.is_recording():
            span_context = span.get_span_context()
            if span_context and span_context.is_valid:
                event_dict["trace_id"] = format(span_context.trace_id, "032x")
                event_dict["span_id"] = format(span_context.span_id, "016x")
    except Exception as e:
        # Log for debugging but otherwise fail silently.
        import logging

        logging.getLogger(__name__).debug(
            "Could not add OTel context to log record.", exc_info=e
        )
        pass
    return event_dict


def get_logger(name: str | None = None) -> Any:
    """Get a logger instance, optionally with a specific name."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger_name=name)
    return logger


def bind_request_id(request_id: str) -> None:
    """Bind request_id to the structlog context for correlation."""
    request_id_ctx.set(request_id)
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_context() -> None:
    """Clear the request context after request processing."""
    request_id_ctx.set(None)
    structlog.contextvars.clear_contextvars()


def get_current_request_id() -> str | None:
    """Get the current request_id from context."""
    return request_id_ctx.get()
