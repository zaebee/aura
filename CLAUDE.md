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

The Core Service uses a pluggable strategy pattern for pricing decisions:

**RuleBasedStrategy**: Deterministic rules without LLM
- Bid < floor_price → Counter offer
- Bid >= floor_price → Accept
- Bid > $1000 → Require UI confirmation

**MistralStrategy**: LLM-based intelligent negotiation
- Uses `langchain_mistralai` with structured output
- Returns decisions with reasoning
- Handles complex negotiation scenarios

Implementation: `core-service/src/llm_strategy.py` defines both strategies. Change strategy in `core-service/src/main.py:171` by instantiating the desired class.

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

## Critical Code Locations

### Protocol Buffer Definitions
- **Service contracts**: `proto/aura/negotiation/v1/negotiation.proto`
- **Generated Python code**: `api-gateway/src/proto/` and `core-service/src/proto/`

### Core Service (gRPC)
- **Main service**: `core-service/src/main.py`
  - `NegotiationService.Negotiate()` at line 63
  - `NegotiationService.Search()` at line 105
- **Pricing strategies**: `core-service/src/llm_strategy.py`
  - `RuleBasedStrategy` at line 34
  - `MistralStrategy` at line 119
- **Database models**: `core-service/src/db.py`
- **Embeddings**: `core-service/src/embeddings.py`

### API Gateway (FastAPI)
- **HTTP endpoints**: `api-gateway/src/main.py`
- **Configuration**: `api-gateway/src/config.py`

### Tests
- **Rule-based strategy tests**: `core-service/tests/test_rule_based_strategy.py`
- **Mistral strategy tests**: `core-service/tests/test_mistral_strategy.py`
- **Test fixtures**: `core-service/tests/conftest.py`

## Configuration and Environment

### Required Environment Variables
```bash
# Core Service
DATABASE_URL=postgresql://user:password@localhost:5432/aura_db
MISTRAL_API_KEY=your_mistral_api_key_here
OTEL_SERVICE_NAME=aura-core
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

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

### Modifying Pricing Strategy

To add a new strategy:
1. Create new class in `core-service/src/llm_strategy.py`
2. Implement `PricingStrategy` protocol with `evaluate()` method
3. Return `negotiation_pb2.NegotiateResponse` with one of: `accepted`, `countered`, `rejected`, or `ui_required`
4. Update `core-service/src/main.py:171` to use new strategy
5. Add tests in `core-service/tests/test_<strategy_name>.py`

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

## Important Notes

- **Auto-generated code**: Never edit files in `*/src/proto/` directories - regenerate with `buf generate`
- **Python version**: Requires Python 3.13+ (see `pyproject.toml:6`)
- **Package manager**: Uses `uv`, not pip or poetry
- **Stateless design**: Both services are stateless and horizontally scalable
- **gRPC port**: Core Service runs on 50051 (configurable)
- **HTTP port**: API Gateway runs on 8000 (configurable)
- **Database**: PostgreSQL with pgvector extension is required for vector search
