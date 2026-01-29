# Observability: Tracing and Metrics in the Hive

This document describes the OpenTelemetry (OTel) tracing and Prometheus metrics implementation for the Aura Platform.

## Overview

The Aura Platform now includes full-stack observability across:
- **API Gateway** (FastAPI)
- **Core Service** (gRPC + SQLAlchemy + LangChain)
- **Database** (PostgreSQL via SQLAlchemy)
- **LLM Calls** (Mistral AI via LangChain)

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│             │    │             │    │             │
│  API Client │───▶│ API Gateway │───▶│ Core Service│
│             │    │ (FastAPI)   │    │ (gRPC)      │
└─────────────┘    └─────────────┘    └─────────────┘
                                      │
                                      ├─────────────┐
                                      │             │
                                      ▼             ▼
                                ┌─────────────┐  ┌─────────────┐
                                │             │  │             │
                                │  Database   │  │  Mistral AI │
                                │ (PostgreSQL)│  │  (LangChain)│
                                └─────────────┘  └─────────────┘
```

All components export traces to **Jaeger** via OTLP protocol.

### Metrics Architecture (The Hive Vital Signs)

In addition to tracing, the hive monitors its vital signs using **Prometheus**.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│             │     │              │     │             │
│ Core Service│────▶│ Prometheus   │────▶│ Grafana     │
│ (Metrics)   │     │ (Storage)    │     │ (Visual)    │
└─────────────┘     └──────────────┘     └─────────────┘
```

The Core Service exposes metrics such as CPU usage, memory consumption, and caching health, which are scraped by Prometheus and used by the `GetSystemStatus` gRPC method.

## Configuration

### Environment Variables

Both services use these environment variables:

```env
# API Gateway
AURA_SERVER__OTEL_SERVICE_NAME=aura-gateway
AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Core Service
AURA_SERVER__OTEL_SERVICE_NAME=aura-core
AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
AURA_SERVER__PROMETHEUS_URL=http://prometheus:9090
```

### Docker Compose

The `compose.yml` file already includes the Jaeger service and proper environment variables:

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    ports:
      - "16686:16686"  # UI
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
```

## Implementation Details

### Telemetry Initialization

Both services initialize OpenTelemetry in their `main.py` files:

```python
# Initialize OpenTelemetry tracing
service_name = settings.otel_service_name
tracer = init_telemetry(service_name, settings.otel_exporter_otlp_endpoint)
```

### Instrumentation

#### API Gateway (`api-gateway/src/main.py`)

- **FastAPI Instrumentation**: Automatic tracing of HTTP requests
- **gRPC Client Instrumentation**: Distributed tracing context propagation

```python
# Instrument FastAPI for automatic tracing
FastAPIInstrumentor.instrument_app(app)

# Instrument gRPC client for distributed tracing
GrpcInstrumentorClient().instrument()
```

#### Core Service (`core-service/src/main.py`)

- **gRPC Server Instrumentation**: Automatic tracing of gRPC methods
- **SQLAlchemy Instrumentation**: Database query tracing
- **LangChain Instrumentation**: LLM call tracing

```python
# Instrument gRPC server for distributed tracing
GrpcInstrumentorServer().instrument()

# Instrument SQLAlchemy for database query tracing
SQLAlchemyInstrumentor().instrument(engine=engine)

# Instrument LangChain for LLM call tracing
LangchainInstrumentor().instrument()
```

### Logging Correlation

Both services include OpenTelemetry context in structlog output:

```python
def add_otel_context(logger, method_name, event_dict):
    """Add OpenTelemetry context to log records."""
    span = get_current_span()
    if span.is_recording():
        span_context = span.get_span_context()
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict
```

Example log output:
```json
{
  "level": "info",
  "event": "request_started",
  "method": "POST",
  "path": "/v1/negotiate",
  "trace_id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
  "span_id": "ab1c2d3e4f5a6b7c",
  "timestamp": "2024-01-01T00:00:00.000000Z"
}
```

## Usage

### Running with Docker

```bash
docker-compose up --build
```

### Accessing Jaeger UI

After starting the services, access the Jaeger UI at:

```
http://localhost:16686
```

### Expected Traces

You should see traces for:

1. **API Gateway Requests**: `/v1/search`, `/v1/negotiate`
2. **gRPC Calls**: `NegotiationService.Negotiate`, `NegotiationService.Search`
3. **Database Queries**: SQLAlchemy queries to PostgreSQL
4. **LLM Calls**: LiteLLM/DSPy inference calls

### Key Metrics

The following vital signs are monitored:

- `cpu_usage_percent`: Average CPU load across the hive cells.
- `memory_usage_mb`: Average memory footprint of the Core Engine.
- `cache_hit_rate`: Success rate of the Semantic Nectar (Redis).
- `negotiation_count`: Number of active economic interactions.

### Testing

Run the telemetry test:

```bash
python test_telemetry.py
```

This will:
1. Test API Gateway endpoints
2. Generate traces for analysis
3. Provide instructions for viewing traces in Jaeger

## Troubleshooting

### No Traces Appearing

1. **Check Jaeger is running**: `docker ps | grep jaeger`
2. **Verify OTLP endpoint**: Ensure `OTEL_EXPORTER_OTLP_ENDPOINT` points to the correct Jaeger instance
3. **Check service logs**: Look for telemetry initialization messages
4. **Verify network connectivity**: Services should be able to reach Jaeger on port 4317

### Common Issues

- **Port conflicts**: Ensure port 4317 is not used by other services
- **Environment variables**: Verify both services have proper OTel environment variables
- **Dependency conflicts**: Ensure all OpenTelemetry packages are compatible versions
- **Fallback behavior**: If OTLP fails, traces are logged to console (check service logs)

### Debugging Commands

```bash
# Check if Jaeger is receiving traces
curl http://localhost:16686/api/traces

# Test OTLP endpoint connectivity
nc -zv jaeger 4317

# Check service logs for telemetry errors
docker logs aura-gateway | grep telemetry
docker logs aura-core | grep telemetry

# Verify environment variables
docker exec aura-gateway env | grep OTEL
docker exec aura-core env | grep OTEL
```

### Error Handling

The implementation includes robust error handling:
- **Fallback to console logging** if OTLP export fails
- **Graceful degradation** if OpenTelemetry initialization fails
- **Input validation** for configuration settings
- **Safe logging context** that doesn't break if OTel is unavailable

## Performance Optimization

### Sampling Configuration

For high-volume environments, consider adding sampling:

```python
from opentelemetry.sdk.trace import sampling

# Add to init_telemetry() before creating provider
sampler = sampling.TraceIdRatioBased(0.5)  # Sample 50% of traces
provider = TracerProvider(resource=resource, sampler=sampler)
```

### Batch Processor Tuning

Adjust batch processor settings for your workload:

```python
# Default settings (good for most cases)
span_processor = BatchSpanProcessor(
    otlp_exporter,
    max_queue_size=2048,
    schedule_delay_millis=5000,  # 5 seconds
    max_export_batch_size=512
)
```

### Resource Usage Monitoring

Monitor OpenTelemetry resource usage:

```bash
# Check memory usage
docker stats aura-gateway aura-core

# Monitor trace export rate
docker logs aura-gateway | grep "span processed"
```

## Advanced Configuration

### Custom Span Attributes

Add business context to traces:

```python
from opentelemetry import trace

# In your API handlers
tracer = trace.get_tracer(__name__)
with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("user.id", user_id)
    span.set_attribute("request.value", amount)
    # Your business logic here
```

### Context Propagation

Manual context propagation for async tasks:

```python
from opentelemetry.context import context
from opentelemetry.trace import get_current_span

# Capture current context
current_context = context.get_current()

# Use in async task
async def background_task():
    with context.attach(current_context):
        # This will have the same trace context
        span = get_current_span()
        span.add_event("background_task_started")
```

## Security Considerations

### Sensitive Data

Avoid logging sensitive data in span attributes:

```python
# ❌ Bad - logs sensitive data
span.set_attribute("user.token", api_token)

# ✅ Good - use metadata or redact
span.set_attribute("user.id", user_id)
span.set_attribute("auth.method", "token")
```

### Network Security

- Ensure OTLP endpoint uses TLS in production
- Restrict Jaeger UI access to authorized personnel
- Consider network policies for inter-service communication

## Migration Guide

### From No Tracing to OpenTelemetry

1. **Start with basic instrumentation** (current implementation)
2. **Add custom spans** for critical business operations
3. **Implement sampling** for high-volume endpoints
4. **Add metrics** for performance monitoring
5. **Set up alerts** based on trace patterns

### Upgrading OpenTelemetry Versions

```bash
# Check for updates
uv add --upgrade opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

# Test in staging first
# Monitor for breaking changes in instrumentation APIs
```

## Dependencies

The following OpenTelemetry packages are used:

```toml
opentelemetry-api>=1.24.0
opentelemetry-sdk>=1.24.0
opentelemetry-exporter-otlp>=1.24.0
opentelemetry-instrumentation-fastapi>=0.45b0
opentelemetry-instrumentation-grpc>=0.45b0
opentelemetry-instrumentation-sqlalchemy>=0.45b0
opentelemetry-instrumentation-langchain>=0.1.0
```

## Performance Considerations

- **Batch processing**: Traces are batched before export to reduce network overhead
- **Sampling**: Consider adding sampling for high-volume environments
- **Resource usage**: OpenTelemetry adds minimal overhead to request processing

## Future Enhancements

- Add metrics collection alongside tracing
- Implement custom span attributes for business context
- Add health checks and monitoring for telemetry pipeline
- Consider adding baggages for additional context propagation
