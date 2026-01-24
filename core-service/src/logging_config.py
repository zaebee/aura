from contextvars import ContextVar

import structlog

# Context variable to store request_id across async boundaries
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def configure_logging() -> None:
    """Configure structlog to output JSON format for structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
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


def get_logger(name: str | None = None) -> structlog.BoundLogger:
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
