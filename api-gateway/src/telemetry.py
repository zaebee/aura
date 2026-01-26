from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def init_telemetry(service_name: str, otlp_endpoint: str = "http://jaeger:4317") -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing with OTLP exporter.

    Args:
        service_name: Name of the service for resource attribution
        otlp_endpoint: OTLP endpoint for exporting traces

    Returns:
        Configured tracer instance
    """
    # Use provided OTLP endpoint or default to Jaeger
    otlp_endpoint = otlp_endpoint or "http://jaeger:4317"

    # Create resource with service name
    resource = Resource.create({"service.name": service_name})

    # Set up tracer provider with resource
    provider = TracerProvider(resource=resource)

    # Set up OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

    # Add batch span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Get tracer for the service
    tracer = trace.get_tracer(service_name)

    return tracer
