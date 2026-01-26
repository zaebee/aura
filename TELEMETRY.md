# OpenTelemetry Instrumentation for Aura Platform

This document describes the OpenTelemetry (OTel) tracing implementation for the Aura Platform.

## Overview

The Aura Platform now includes distributed tracing across:
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

## Configuration

### Environment Variables

Both services use these environment variables:

```env
# API Gateway
OTEL_SERVICE_NAME=aura-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317

# Core Service
OTEL_SERVICE_NAME=aura-core
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
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
  "trace_id": "1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p",
  "span_id": "ab1c2d3e4f5g6h7i",
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
4. **LLM Calls**: Mistral AI calls via LangChain

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