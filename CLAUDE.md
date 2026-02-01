# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Aura is a distributed microservices platform for autonomous economic negotiations between AI agents and service providers. The platform uses:
- **API Gateway** (FastAPI): HTTP/JSON endpoints with rate limiting and signature verification
- **Core Service** (gRPC): Business logic, pricing strategies, and semantic search
- **Protocol Buffers**: Contract-first API design for service communication
- **PostgreSQL with pgvector**: Vector embeddings for semantic search
- **OpenTelemetry**: Distributed tracing with Jaeger

## Development Commands

### Setup and Dependencies
```bash
# Install dependencies
uv sync

# Install development dependencies (linting, testing)
uv sync --group dev

# Generate Protocol Buffer code (MUST run after modifying .proto files)
buf generate
```

### Running Services

#### Using Docker Compose (Recommended)
```bash
# Start all services (PostgreSQL, Core Service, API Gateway, Jaeger)
docker-compose up --build

# The services will be available on:
# - API Gateway: http://localhost:8000
# - Core Service gRPC: localhost:50051
# - Jaeger UI: http://localhost:16686
# - PostgreSQL: localhost:5432
```

#### Running Individually
```bash
# Core Service (from project root)
cd core-service && uv run python -m src.main

# API Gateway (from project root)
cd api-gateway && uv run python -m src.main
```

### Testing
```bash
# Run all tests
make test

# Run with coverage report
make test-cov

# Run with verbose output
make test-verbose

# Run specific test file
uv run pytest core-service/tests/test_rule_based_strategy.py -v
```

### Code Quality
```bash
# Lint code (using ruff)
make lint

# Format code (using ruff)
make format

# Lint Protocol Buffer definitions
buf lint
```

### Database Operations
```bash
# Run migrations
docker-compose exec core-service alembic upgrade head

# Create new migration
docker-compose exec core-service alembic revision --autogenerate -m "description"

# Downgrade migration
docker-compose exec core-service alembic downgrade -1

# Connect to PostgreSQL
docker-compose exec db psql -U user -d aura_db
```

### Simulators and Testing Tools
```bash
# Agent negotiation simulator
python agent_sim.py

# Search functionality simulator
python search_sim.py

# Comprehensive telemetry test
python test_telemetry_comprehensive.py

# Health check endpoints test
python test_health_endpoints.py
```

### Health Checks
```bash
# Test health endpoints
curl http://localhost:8000/healthz   # Liveness
curl http://localhost:8000/readyz    # Readiness
curl http://localhost:8000/health    # Detailed status

# Test infrastructure monitoring
curl http://localhost:8000/v1/system/status  # Prometheus metrics (CPU, memory)

# Check Docker Compose health status
docker-compose ps

# Test gRPC health (requires grpc_health_probe)
grpc_health_probe -addr=localhost:50051
```

## Architecture Patterns

### Contract-First Design with Protocol Buffers

All APIs are defined in `proto/aura/negotiation/v1/negotiation.proto`. The workflow is:

1. **Modify .proto file** to add/change service definitions
2. **Run `buf generate`** to regenerate Python code in both services
3. **Update implementations** in core-service/src/main.py (gRPC handler) and api-gateway/src/main.py (HTTP endpoint)
4. **Generated code lives in** `*/src/proto/` directories and should NEVER be manually edited

### Service Communication Flow

```
HTTP Client → API Gateway (FastAPI:8000) → Core Service (gRPC:50051) → PostgreSQL/Mistral AI
```

- API Gateway converts HTTP/JSON to gRPC/Protobuf
- Core Service handles all business logic
- Both services are **stateless** for horizontal scalability
- Request IDs flow through all layers for distributed tracing

### Pricing Strategy Pattern

The Core Service uses a pluggable strategy pattern for pricing decisions, configured via the `LLM_MODEL` environment variable:

**RuleBasedStrategy** (`LLM_MODEL=rule`): Deterministic rules without LLM
- Bid < floor_price → Counter offer
- Bid >= floor_price → Accept
- Bid > $1000 → Require UI confirmation
- No API key required
- Fastest response time

**LiteLLMStrategy** (any other `LLM_MODEL` value): LLM-based intelligent negotiation
- Supports any provider via litellm (OpenAI, Mistral, Anthropic, Ollama, etc.)
- Uses Jinja2 prompt templates from `core-service/src/prompts/system.md`
- Returns decisions with reasoning
- Handles complex negotiation scenarios
- Example models: `mistral/mistral-large-latest`, `openai/gpt-4o`, `ollama/mistral`

Implementation:
- Strategy factory: `core-service/src/main.py:create_strategy()`
- Rule-based: `core-service/src/llm_strategy.py:RuleBasedStrategy`
- LiteLLM: `core-service/src/llm/strategy.py:LiteLLMStrategy`
- LLM engine: `core-service/src/llm/engine.py:LLMEngine`

### Vector Embeddings and Semantic Search

The Search endpoint (`/v1/search`) uses pgvector for semantic search:

1. **Query text** → `generate_embedding()` → **vector embedding**
2. **Vector similarity search** in PostgreSQL using cosine distance
3. **Results ranked by similarity** with configurable thresholds

Implementation: `core-service/src/embeddings.py` generates embeddings, `core-service/src/main.py:105-167` handles search logic.

### Hidden Knowledge Pattern

**Floor prices are never exposed to clients**. This prevents agents from gaming the system:
- The API Gateway never sees floor prices
- Core Service enforces floor price logic internally
- Agents only receive accept/counter/reject responses
- Database schema includes both `base_price` (public) and `floor_price` (hidden)

### Request ID Propagation

Request IDs flow through the entire system for distributed tracing:
1. API Gateway generates request_id
2. Passed as gRPC metadata (`x-request-id`)
3. Core Service extracts and binds to logging context
4. All logs and traces include the request_id

Implementation: `logging_config.py` provides `bind_request_id()` and `clear_request_context()` helpers.

### Infrastructure Monitoring ("The Eyes")

The Core Service can query its own infrastructure health from Prometheus:
- Endpoint: `GET /v1/system/status` (API Gateway) → `GetSystemStatus` RPC (Core Service)
- Metrics: CPU usage (%), Memory usage (MB), timestamp, cached status
- Caching: 30-second TTL to reduce Prometheus load
- Graceful degradation: Returns cached data or error dict on failure

Implementation:
- Prometheus client: `core-service/src/monitor.py:get_hive_metrics()`
- Cache layer: `core-service/src/monitor.py:MetricsCache`
- gRPC handler: `core-service/src/main.py:GetSystemStatus()`
- HTTP endpoint: `api-gateway/src/main.py:/v1/system/status`

## Critical Code Locations

### Protocol Buffer Definitions
- **Service contracts**: `proto/aura/negotiation/v1/negotiation.proto`
- **Generated Python code**: `api-gateway/src/proto/` and `core-service/src/proto/`

### Core Service (gRPC)
- **Main service**: `core-service/src/main.py`
  - `NegotiationService.Negotiate()` handler
  - `NegotiationService.Search()` handler
  - `NegotiationService.GetSystemStatus()` handler
  - `create_strategy()` factory for pricing strategy selection
- **Pricing strategies**:
  - `RuleBasedStrategy`: `core-service/src/llm_strategy.py`
  - `LiteLLMStrategy`: `core-service/src/llm/strategy.py`
  - `LLMEngine`: `core-service/src/llm/engine.py`
- **Infrastructure monitoring**: `core-service/src/monitor.py`
- **Prompt templates**: `core-service/src/prompts/system.md`
- **Database models**: `core-service/src/db.py`
- **Embeddings**: `core-service/src/embeddings.py`

### API Gateway (FastAPI)
- **HTTP endpoints**: `api-gateway/src/main.py`
- **Configuration**: `api-gateway/src/config.py`

### Tests
- **Rule-based strategy tests**: `core-service/tests/test_rule_based_strategy.py`
- **LiteLLM strategy tests**: `core-service/tests/test_litellm_strategy.py`
- **Test fixtures**: `core-service/tests/conftest.py`

## Configuration and Environment

### Required Environment Variables
```bash
# Core Service
DATABASE_URL=postgresql://user:password@localhost:5432/aura_db
OTEL_SERVICE_NAME=aura-core
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# LLM Configuration (choose one strategy)
LLM_MODEL=rule                              # No LLM, no API key needed
# OR
LLM_MODEL=mistral/mistral-large-latest      # Requires MISTRAL_API_KEY
MISTRAL_API_KEY=sk-xxx
# OR
LLM_MODEL=openai/gpt-4o                     # Requires OPENAI_API_KEY
OPENAI_API_KEY=sk-proj-xxx
# OR
LLM_MODEL=anthropic/claude-3-5-sonnet-20241022  # Requires ANTHROPIC_API_KEY
ANTHROPIC_API_KEY=sk-ant-xxx
# OR
LLM_MODEL=ollama/mistral                    # No API key (assumes Ollama running locally)

# Infrastructure Monitoring
PROMETHEUS_URL=http://prometheus-kube-prometheus-prometheus.monitoring:9090

# API Gateway
CORE_SERVICE_HOST=localhost:50051
OTEL_SERVICE_NAME=aura-gateway
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### Configuration Files
- **Python dependencies**: `pyproject.toml` (uses uv package manager)
- **Docker services**: `compose.yml`
- **Protocol Buffer config**: `buf.yaml` and `buf.gen.yaml`
- **Ruff linting**: Configured in `pyproject.toml` (excludes `**/proto/**`)

## Common Development Workflows

### Adding a New API Endpoint

1. Define in `proto/aura/negotiation/v1/negotiation.proto`:
   ```proto
   service NegotiationService {
       rpc NewEndpoint (NewRequest) returns (NewResponse);
   }
   ```
2. Run `buf generate` to regenerate code
3. Implement gRPC handler in `core-service/src/main.py`
4. Add HTTP endpoint in `api-gateway/src/main.py`
5. Add tests in `core-service/tests/`

### Changing LLM Models

To switch between LLM providers or use rule-based strategy:

**Via Environment Variable** (Recommended):
```bash
# Rule-based (no LLM)
export LLM_MODEL=rule

# Mistral (backward compatible)
export LLM_MODEL=mistral/mistral-large-latest
export MISTRAL_API_KEY=sk-xxx

# OpenAI
export LLM_MODEL=openai/gpt-4o
export OPENAI_API_KEY=sk-proj-xxx

# Ollama (local)
export LLM_MODEL=ollama/mistral

# Then restart services
docker-compose restart core-service
```

**Via Helm** (Kubernetes deployment):
```bash
# Deploy with OpenAI
helm install aura deploy/aura \
  --set core.env.LLM_MODEL="openai/gpt-4o" \
  --set secrets.openaiApiKey="sk-proj-xxx"

# Deploy with rule-based (no LLM)
helm install aura deploy/aura \
  --set core.env.LLM_MODEL="rule"
```

### Modifying Pricing Strategy

To add a new pricing strategy:
1. Create new class in `core-service/src/llm/` or `core-service/src/llm_strategy.py`
2. Implement `PricingStrategy` protocol with `evaluate()` method
3. Return `negotiation_pb2.NegotiateResponse` with one of: `accepted`, `countered`, `rejected`, or `ui_required`
4. Update `core-service/src/main.py:create_strategy()` factory to instantiate your strategy
5. Add tests in `core-service/tests/test_<strategy_name>.py`

### Customizing Prompt Templates

To modify LLM prompts:
1. Edit `core-service/src/prompts/system.md` (Jinja2 template)
2. Available variables: `business_type`, `item_name`, `base_price`, `floor_price`, `market_load`, `trigger_price`, `bid`, `reputation`
3. Test changes: `docker-compose restart core-service`

### Database Schema Changes

1. Modify models in `core-service/src/db.py`
2. Create migration: `docker-compose exec core-service alembic revision --autogenerate -m "description"`
3. Review generated migration in `core-service/migrations/versions/`
4. Apply migration: `docker-compose exec core-service alembic upgrade head`

## Observability

### Distributed Tracing
- **Jaeger UI**: http://localhost:16686
- **Instrumented components**: FastAPI, gRPC, SQLAlchemy, LangChain
- **Trace propagation**: Request IDs flow through all services

### Logging
- **Format**: Structured JSON logs with `structlog`
- **Request correlation**: All logs include `request_id`
- **Log levels**: Configured in `*_config.py` files

### Viewing Traces
```bash
# Follow logs for specific service
docker-compose logs -f core-service
docker-compose logs -f api-gateway

# View all logs
docker-compose logs -f
```

## Migration Guide

### Upgrading from Hardcoded Mistral to LiteLLM

If you're upgrading from the old hardcoded `MistralStrategy`:

**Before** (hardcoded Mistral):
```python
# core-service/src/main.py
from llm_strategy import MistralStrategy
strategy = MistralStrategy()

# .env
MISTRAL_API_KEY=sk-xxx
```

**After** (flexible litellm):
```bash
# .env - Option 1: Keep using Mistral (backward compatible)
LLM_MODEL=mistral/mistral-large-latest
MISTRAL_API_KEY=sk-xxx

# .env - Option 2: Switch to OpenAI
LLM_MODEL=openai/gpt-4o
OPENAI_API_KEY=sk-proj-xxx

# .env - Option 3: Use local Ollama (no API key)
LLM_MODEL=ollama/mistral

# .env - Option 4: No LLM (rule-based only)
LLM_MODEL=rule
```

**Code changes required**: **None** - Configuration-driven via environment variables.

**Test changes**: If you have custom tests importing `MistralStrategy`, update imports:
```python
# Before
from llm_strategy import MistralStrategy

# After
from llm.strategy import LiteLLMStrategy
```

**Backward compatibility**: Default `LLM_MODEL=mistral/mistral-large-latest` maintains identical behavior to the old `MistralStrategy`.

## Important Notes

- **Auto-generated code**: Never edit files in `*/src/proto/` directories - regenerate with `buf generate`
- **Python version**: Requires Python 3.12+ (see `pyproject.toml:6`)
- **Package manager**: Uses `uv`, not pip or poetry
- **Stateless design**: Both services are stateless and horizontally scalable
- **gRPC port**: Core Service runs on 50051 (configurable)
- **HTTP port**: API Gateway runs on 8000 (configurable)
- **Database**: PostgreSQL with pgvector extension is required for vector search
- **LLM flexibility**: Supports 100+ models via litellm (OpenAI, Anthropic, Mistral, Ollama, etc.)
