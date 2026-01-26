import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# TODO: Consider refactoring this into a shared package to avoid duplication
# between api-gateway and core-service. For now, duplication is acceptable
# to keep each service independent and avoid complex dependency management.


def init_telemetry(
    service_name: str, otlp_endpoint: str = "http://jaeger:4317"
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing with OTLP exporter.

    Args:
        service_name: Name of the service for resource attribution
        otlp_endpoint: OTLP endpoint for exporting traces

    Returns:
        Configured tracer instance

    Raises:
        ValueError: If service_name is not provided
    """
    service_name = service_name.lower().strip()
    if not service_name:
        raise ValueError(
            "service_name must be provided for OpenTelemetry initialization"
        )

    # Create resource with service name
    resource = Resource.create({"service.name": service_name})

    # Set up tracer provider with resource
    provider = TracerProvider(resource=resource)

    # Set up OTLP exporter with error handling
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)

    except Exception as e:
        logging.warning(
            f"Failed to initialize OTLP exporter, falling back to console exporter: {e}"
        )
        # Fallback to console exporter only
        console_exporter = ConsoleSpanExporter()
        span_processor = BatchSpanProcessor(console_exporter)
        provider.add_span_processor(span_processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Get tracer for the service
    tracer = trace.get_tracer(service_name)

    return tracer
