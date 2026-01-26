# Aura Platform

Aura is a distributed microservices platform for autonomous economic negotiations between AI agents and service providers. It provides a scalable architecture with separate API Gateway and Core Service components, using Protocol Buffers for efficient communication and gRPC for internal service-to-service communication.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- uv (Python package manager) - `pip install uv`
- buf (Protocol Buffer toolkit) - [Installation Guide](https://buf.build/docs/installation)
- Docker and Docker Compose
- Mistral AI API key (for LLM-based negotiation)

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/zaebee/aura.git
   cd aura
   ```

2. **Install Python dependencies:**
   ```bash
   uv sync
   ```

3. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Mistral API key
   ```

4. **Generate Protocol Buffer code:**
   ```bash
   buf generate
   ```

## 🏗️ Running the Platform

### Using Docker Compose (Recommended)

```bash
# Start all services (PostgreSQL, Core Service, API Gateway, Jaeger)
docker-compose up --build
```

This will start:
- PostgreSQL with pgvector extension (port 5432)
- Core Service (gRPC on port 50051)
- API Gateway (HTTP on port 8000)
- Jaeger for distributed tracing (UI on port 16686)

### Running Services Individually

**Core Service:**
```bash
cd core-service
uv run python -m src.main
```

**API Gateway:**
```bash
cd api-gateway
uv run python -m src.main
```

## 🧪 Testing and Simulation

### Run Tests
```bash
# Run all tests
make test

# Run tests with coverage
make test-cov
```

### Run Simulators

**Agent Negotiation Simulator:**
```bash
python agent_sim.py
```

**Search Simulator:**
```bash
python search_sim.py
```

## 📂 Project Structure

```
aura/
├── proto/                 # Protocol Buffer definitions
│   ├── aura/
│   │   └── negotiation/
│   │       └── v1/
│   │           └── negotiation.proto
│   ├── buf.yaml          # Buf configuration
│   └── buf.gen.yaml      # Code generation config
├── api-gateway/          # API Gateway service (FastAPI)
│   ├── src/
│   │   ├── main.py       # HTTP endpoints and routing
│   │   └── proto/        # Generated protobuf code
│   └── Dockerfile
├── core-service/         # Core business logic service
│   ├── src/
│   │   ├── main.py       # gRPC service implementation
│   │   ├── llm_strategy.py # LLM-based negotiation logic
│   │   ├── db.py          # Database models and connections
│   │   ├── embeddings.py  # Vector embedding generation
│   │   └── proto/        # Generated protobuf code
│   ├── tests/            # Unit and integration tests
│   └── Dockerfile
├── docs/                 # Documentation
│   ├── ARCHITECTURE.md   # System architecture
│   └── TELEMETRY.md      # Observability setup
├── agent_sim.py          # Agent negotiation simulator
├── search_sim.py         # Search functionality simulator
├── compose.yml           # Docker Compose configuration
├── pyproject.toml        # Python dependencies
├── uv.lock              # Lock file
└── Makefile              # Common development tasks
```

## 🔧 Development Workflow

### Code Generation
After modifying `.proto` files:
```bash
buf generate
```

### Linting and Formatting
```bash
# Lint code
make lint

# Format code
make format
```

### Database Migrations
```bash
# Run migrations
docker-compose exec core-service alembic upgrade head

# Create new migration
docker-compose exec core-service alembic revision --autogenerate -m "description"
```

## 📖 API Endpoints

### Negotiation Endpoint
```
POST /v1/negotiate
```

**Request:**
```json
{
  "item_id": "hotel_alpha",
  "bid_amount": 850.0,
  "currency": "USD",
  "agent_did": "did:agent:007"
}
```

**Response:**
```json
{
  "session_token": "sess_...",
  "status": "accepted",
  "valid_until": 1234567890,
  "data": {
    "final_price": 850.0,
    "reservation_code": "MISTRAL-1234567890"
  }
}
```

### Search Endpoint
```
POST /v1/search
```

**Request:**
```json
{
  "query": "Luxury stay with spa and ocean view",
  "limit": 3
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "hotel_alpha",
      "name": "Luxury Beach Resort",
      "price": 1000.0,
      "score": 0.95,
      "details": "5-star resort with private beach"
    }
  ]
}
```

## 🔒 Security

The platform uses:
- **Signed Headers**: Agents must sign requests with `X-Agent-ID`, `X-Timestamp`, and `X-Signature`
- **Rate Limiting**: Prevents abuse through Redis-backed rate limiting
- **Hidden Knowledge**: Floor prices are never exposed to agents
- **JWT Authentication**: For agent identity verification

## 📊 Observability

- **Distributed Tracing**: Jaeger integration for end-to-end request tracing
- **Structured Logging**: JSON logging with request IDs
- **Metrics**: OpenTelemetry for performance monitoring

## 🤝 Contributing

1. Follow the existing code style
2. Update Protocol Buffers as needed
3. Regenerate code after proto changes (`buf generate`)
4. Add tests for new functionality
5. Update documentation

## 📄 License

This project is licensed under the [MIT License](LICENSE).