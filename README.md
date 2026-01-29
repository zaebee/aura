# Aura Platform

Aura is a distributed microservices platform for autonomous economic negotiations between AI agents and service providers. It provides a scalable architecture with separate API Gateway and Core Service components, using Protocol Buffers for efficient communication and gRPC for internal service-to-service communication.

## 🏗️ Architecture

```mermaid
graph TD
    subgraph Clients ["Clients (Agents)"]
        Browser["Agent Console (Next.js)"]
        Telegram["Telegram Bot"]
        MCP["MCP Server (Claude/Cursor)"]
    end

    subgraph Infrastructure ["Aura Platform"]
        Gateway["API Gateway (FastAPI)"]
        Core["Core Service (gRPC/Python)"]

        DB[("PostgreSQL (pgvector)")]
        Redis[("Redis (Cache/RateLimit)")]
        Prometheus[("Prometheus (Metrics)")]
    end

    subgraph External ["External Services"]
        Mistral["Mistral AI (Brain)"]
        Solana["Solana Network (Payments)"]
    end

    %% Connections
    Browser -- "Signed HTTP" --> Gateway
    Telegram -- "gRPC" --> Core
    MCP -- "Signed HTTP" --> Gateway

    Gateway -- "gRPC" --> Core
    Gateway -. "Rate Limit" .-> Redis

    Core -- "Vector Search" --> DB
    Core -- "Cache" --> Redis
    Core -- "Brain (DSPy)" --> Mistral
    Core -- "Payments" --> Solana
    Core -. "Metrics" .-> Prometheus
```

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- uv (Python package manager) - `pip install uv`
- buf (Protocol Buffer toolkit) - [Installation Guide](https://buf.build/docs/installation)
- Docker and Docker Compose
- Mistral AI API key (for LLM-based negotiation)
- Redis and PostgreSQL (provided via Docker)

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
   # Edit .env and add your API keys using the new nested structure:
   # AURA_LLM__API_KEY="your_mistral_key"
   # AURA_DATABASE__URL="postgresql://user:password@localhost:5432/aura_db"
   ```

4. **Train the Brain (DSPy):**
   ```bash
   uv run core-service/train_dspy.py
   ```

5. **Generate Protocol Buffer code:**
   ```bash
   buf generate
   ```

## 🏗️ Running the Platform

### Using Docker Compose (Recommended)

```bash
# Start all services (PostgreSQL, Redis, Core, Gateway, Telegram Bot, Prometheus)
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
├── api-gateway/          # API Gateway service (FastAPI)
├── core-service/         # Core business logic service (DSPy Engine)
├── adapters/             # External interface adapters
│   ├── telegram-bot/     # Telegram Bot interface
│   └── mcp-server/       # Model Context Protocol (MCP) server
├── docs/                 # Detailed documentation
├── frontend/             # Next.js Agent Console
├── compose.yml           # Docker Compose configuration
├── pyproject.toml        # Python dependencies
└── Makefile              # Common development tasks
```

### Services & Adapters

- **Core Service**: The brain of the platform. Uses DSPy for ML-optimized negotiation strategies and PostgreSQL/pgvector for semantic search.
- **API Gateway**: Secure entry point for autonomous agents. Handles signature verification and rate limiting.
- **Telegram Bot**: User-friendly interface for manual search and negotiation via Telegram.
- **MCP Server**: Allows AI agents (Claude/Cursor) to natively use Aura tools.

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

The platform now includes **cryptographic signature verification** using Ed25519:

### Security Features

- **Signed Headers**: Agents must sign requests with `X-Agent-ID`, `X-Timestamp`, and `X-Signature`
- **Replay Protection**: Timestamps validated within ±60 seconds
- **Request Integrity**: Body hash included in signature to prevent tampering
- **Agent Authentication**: DID-based identity verification using Ed25519
- **Rate Limiting**: Prevents abuse through Redis-backed rate limiting
- **Hidden Knowledge**: Floor prices are never exposed to agents

### Running with Security

1. **Generate agent keys**:
   ```python
   from agent_identity import AgentWallet
   wallet = AgentWallet()
   print(f"DID: {wallet.did}")
   print(f"Private Key: {wallet.private_key_hex}")
   ```

2. **Run the secure gateway**:
   ```bash
   cd api-gateway
   uv run python -m src.main
   ```

3. **Run secure simulators**:
   ```bash
   python agent_sim.py
   python autonomous_buyer.py
   ```

4. **Test security**:
   ```bash
   python test_security.py
   ```

### Security Implementation Details

- **Algorithm**: Ed25519 (PyNaCl library)
- **Signature Format**: `METHOD + PATH + TIMESTAMP + BodyHash`
- **DID Format**: `did:key:public_key_hex`
- **Timestamp Validation**: ±60 seconds tolerance for clock skew

See `docs/SECURITY.md` for comprehensive security documentation.

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