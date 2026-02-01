# Aura Platform - Developer Guide

## 🚀 Getting Started

Welcome to the Aura Platform developer guide! This document provides step-by-step instructions for setting up your development environment, running the platform, and contributing to the project.

## 📋 Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.8+ | Core development language |
| uv | Latest | Python package manager |
| buf | Latest | Protocol Buffer toolkit |
| Docker | Latest | Containerization |
| Docker Compose | Latest | Multi-container orchestration |
| Git | Latest | Version control |
| Make | Latest | Build automation |

### Optional Software

| Software | Purpose |
|----------|---------|
| PostgreSQL | Local database development |
| Redis | Local caching development |
| Jaeger | Distributed tracing UI |
| Mistral AI Account | LLM-based negotiation testing |

## 🏗️ Setup Instructions

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/zaebee/aura.git
cd aura

# Check out the main branch
git checkout main
```

### 2. Install Python Dependencies

```bash
# Install uv if you haven't already
pip install uv

# Install project dependencies
uv sync

# Install development dependencies (optional)
uv sync --group dev
```

### 3. Set Up Environment Variables

Aura uses a modular configuration system powered by **Pydantic V2 Settings**. Environment variables are prefixed with `AURA_` and use `__` (double underscore) as a nested delimiter.

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with the new nested structure
# AURA_LLM__API_KEY="your_api_key"
# AURA_DATABASE__URL="postgresql://user:password@localhost:5432/aura_db"
# AURA_DATABASE__REDIS_URL="redis://localhost:6379/0"

nano .env
```

#### Configuration Mapping

| Domain | Config Class | Env Prefix | Description |
|--------|--------------|------------|-------------|
| Database | `DatabaseSettings` | `AURA_DATABASE__` | Postgres and Redis connections |
| LLM | `LLMSettings` | `AURA_LLM__` | Model selection and API keys |
| Server | `ServerSettings` | `AURA_SERVER__` | gRPC/HTTP ports and Telemetry |
| Crypto | `CryptoSettings` | `AURA_CRYPTO__` | Solana RPC and Private keys |

### 4. Install buf (Protocol Buffer Toolkit)

Follow the official installation guide: [https://buf.build/docs/installation](https://buf.build/docs/installation)

```bash
# Verify installation
buf --version
```

### 5. Generate Protocol Buffer Code

```bash
# Generate Python code from .proto files
buf generate

# This will create generated code in:
# - api-gateway/src/proto/
# - core-service/src/proto/
```

## 🏃 Running the Platform

### Using Docker Compose (Recommended)

```bash
# Start all services
docker-compose up --build

# This will start:
# - PostgreSQL with pgvector (port 5432)
# - Core Service (gRPC on port 50051)
# - API Gateway (HTTP on port 8000)
# - Jaeger for tracing (UI on port 16686)
```

### Running Services Individually

#### Core Service

**1. Train the Brain (Mandatory)**
Before running the Core service, you must train the DSPy-based negotiation engine:
```bash
uv run core-service/train_dspy.py
```

**2. Run the Service**
```bash
# Navigate to core-service directory
cd core-service

# Run the core service
uv run python -m src.main

# The service will be available on gRPC port 50051
```

#### API Gateway

```bash
# Navigate to api-gateway directory
cd api-gateway

# Run the API gateway
uv run python -m src.main

# The gateway will be available on HTTP port 8000
```

### Running with Hot Reload (Development)

```bash
# For core service (requires watchfiles)
cd core-service
uv run python -m src.main --reload

# For API gateway
cd api-gateway
uv run python -m src.main --reload
```

## 🧪 Testing and Quality Assurance

### Running Tests

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run tests with verbose output
make test-verbose
```

### Code Quality

```bash
# Lint code (using ruff)
make lint

# Format code (using ruff)
make format

# Check Protocol Buffer definitions
buf lint
```

### Running Simulators

```bash
# Agent negotiation simulator
python agent_sim.py

# Search functionality simulator
python search_sim.py
```

## 📦 Database Setup

### PostgreSQL Requirement

Aura now requires **PostgreSQL with pgvector** for all environments. SQLite is no longer supported due to the requirement for vector similarity search and complex concurrent negotiations.

### Running Migrations

```bash
# Run database migrations
docker-compose exec core-service alembic upgrade head

# Create a new migration
docker-compose exec core-service alembic revision --autogenerate -m "add_new_feature"

# Downgrade migrations
docker-compose exec core-service alembic downgrade -1
```

### Seeding the Database

```bash
# Seed initial data
docker-compose exec core-service python -m src.seed
```

### Connecting to PostgreSQL

```bash
# Connect to the database
docker-compose exec db psql -U user -d aura_db

# Common commands:
# \dt - List tables
# SELECT * FROM inventory_items LIMIT 10;
# \q - Quit
```

## 🔧 Development Workflow

### Making Changes to Protocol Buffers

1. **Edit the .proto file**:
   ```bash
   nano proto/aura/negotiation/v1/negotiation.proto
   ```

2. **Regenerate code**:
   ```bash
   buf generate
   ```

3. **Update implementations**:
   - Update API Gateway handlers
   - Update Core Service implementations
   - Update any tests

4. **Test changes**:
   ```bash
   make test
   ```

### Adding New Features

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Implement the feature**:
   - Add new Protocol Buffer definitions if needed
   - Implement backend logic in core-service
   - Add API endpoints in api-gateway
   - Write tests

3. **Update documentation**:
   - Update README.md if needed
   - Update API_SPECIFICATION.md if new endpoints
   - Update ARCHITECTURE.md if architectural changes

4. **Commit changes**:
   ```bash
   git add .
git commit -m "feat(negotiation): add new negotiation strategy"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   # Create Pull Request on GitHub
   ```

### Debugging

```bash
# View logs for a specific service
docker-compose logs core-service

# Follow logs in real-time
docker-compose logs -f api-gateway

# Access service shell
docker-compose exec core-service bash

# Check running containers
docker-compose ps
```

## 🔍 Observability and Monitoring

### Distributed Tracing with Jaeger

```bash
# Access Jaeger UI
open http://localhost:16686

# Features:
# - View service map
# - Search for specific traces
# - Analyze request latency
# - Identify performance bottlenecks
```

### Logging

```bash
# View application logs
docker-compose logs -f

# Log structure:
# - JSON formatted for easy parsing
# - Includes request IDs for traceability
# - Structured fields for filtering
```

### Metrics

The platform uses OpenTelemetry for metrics collection. You can integrate with:
- Prometheus
- Grafana
- Datadog
- New Relic

## 🛠️ Common Development Tasks

### Adding a New Pricing Strategy

1. **Create a new strategy class**:
   ```python
   # In core-service/src/llm_strategy.py
   class NewStrategy:
       def evaluate(self, item_id, bid, reputation, request_id):
           # Your logic here
           return negotiation_pb2.NegotiateResponse()
   ```

2. **Implement the PricingStrategy protocol**:
   ```python
   from typing import Protocol
   
   class PricingStrategy(Protocol):
       def evaluate(self, item_id: str, bid: float, reputation: float, request_id: str | None) -> negotiation_pb2.NegotiateResponse: ...
   ```

3. **Update the service to use your strategy**:
   ```python
   # In core-service/src/main.py
   strategy = NewStrategy()  # Instead of MistralStrategy()
   ```

### Adding New API Endpoints

1. **Define the endpoint in Protocol Buffers**:
   ```proto
   # In proto/aura/negotiation/v1/negotiation.proto
   service NegotiationService {
       rpc NewEndpoint (NewRequest) returns (NewResponse);
   }
   ```

2. **Regenerate code**:
   ```bash
   buf generate
   ```

3. **Implement in Core Service**:
   ```python
   # In core-service/src/main.py
   def NewEndpoint(self, request, context):
       # Your implementation
       return NewResponse()
   ```

4. **Add HTTP endpoint in API Gateway**:
   ```python
   # In api-gateway/src/main.py
   @app.post("/v1/new-endpoint")
   async def new_endpoint(payload: NewRequestHTTP):
       # Convert to gRPC and call core service
   ```

### Working with Vector Embeddings

```python
# Generate embeddings
from embeddings import generate_embedding

query = "Luxury hotel with ocean view"
embedding = generate_embedding(query)

# Use in semantic search
session = SessionLocal()
results = session.query(InventoryItem)
    .order_by(InventoryItem.embedding.cosine_distance(embedding))
    .limit(5)
    .all()
```

## 📚 Project Structure Deep Dive

### Protocol Buffers (`proto/`)

```
aura/proto/
├── aura/
│   └── negotiation/
│       └── v1/
│           └── negotiation.proto  # Main service definitions
├── buf.yaml                      # Buf configuration
└── buf.gen.yaml                 # Code generation config
```

**Key Concepts**:
- **Service Definitions**: Define gRPC services and methods
- **Message Types**: Define data structures for requests/responses
- **Versioning**: Organized by version (v1/)
- **Code Generation**: `buf generate` creates Python classes

### Core Service (`core-service/`)

```
aura/core-service/
├── src/
│   ├── main.py                  # gRPC service implementation
│   ├── llm_strategy.py           # Pricing strategies
│   ├── db.py                     # Database models and connections
│   ├── embeddings.py             # Vector embedding generation
│   ├── config.py                 # Configuration management
│   ├── logging_config.py         # Logging setup
│   ├── telemetry.py              # OpenTelemetry integration
│   └── proto/                    # Generated protobuf code
├── tests/                       # Unit and integration tests
├── migrations/                  # Database migration scripts
└── Dockerfile                   # Container configuration
```

**Key Components**:
- **gRPC Server**: Handles incoming requests from API Gateway
- **Pricing Strategies**: Rule-based and LLM-based decision making
- **Database Layer**: SQLAlchemy models and pgvector integration
- **Embedding Generation**: Text to vector conversion for search

### API Gateway (`api-gateway/`)

```
aura/api-gateway/
├── src/
│   ├── main.py                  # FastAPI application
│   ├── config.py                 # Configuration management
│   ├── logging_config.py         # Logging setup
│   ├── telemetry.py              # OpenTelemetry integration
│   └── proto/                    # Generated protobuf code
└── Dockerfile                   # Container configuration
```

**Key Components**:
- **FastAPI Application**: RESTful API endpoints
- **Request Validation**: Header verification and rate limiting
- **gRPC Client**: Communication with Core Service
- **Error Handling**: Graceful responses and logging

## 🔒 Security Considerations

### Signature Verification

The platform uses Ed25519 signatures for request authentication:

```python
# Example signature verification (conceptual)
import ed25519

def verify_signature(agent_id, timestamp, signature, body_hash):
    # Get agent's public key from database
    public_key = get_agent_public_key(agent_id)
    
    # Verify signature
    message = f"{method}{path}{timestamp}{body_hash}"
    return ed25519.verify(signature, message, public_key)
```

### Rate Limiting

```python
# Rate limiting implementation (conceptual)
from redis import Redis

def check_rate_limit(agent_id):
    redis = Redis()
    key = f"rate_limit:{agent_id}"
    
    # Check current count
    count = redis.incr(key)
    
    # Set expiration if first request
    if count == 1:
        redis.expire(key, 60)  # 60 second window
    
    return count <= 100  # Allow 100 requests per minute
```

### JWT Authentication

```python
# JWT verification (conceptual)
import jwt
from fastapi import Header, HTTPException

def verify_jwt(x_agent_token: str = Header(None)):
    if not x_agent_token:
        raise HTTPException(status_code=401, detail="Missing token")
    
    try:
        payload = jwt.decode(x_agent_token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

## 🤝 Contributing Guidelines

### Code Style

- **Python**: Follow PEP 8 guidelines
- **Type Hints**: Use Python type hints extensively
- **Docstrings**: Use Google-style docstrings
- **Imports**: Group imports (standard library, third-party, local)
- **Naming**: Use snake_case for variables/functions, CamelCase for classes

### Commit Messages

- **Format**: `<type>(<scope>): <description>`
- **Types**: feat, fix, docs, style, refactor, perf, test, chore
- **Examples**:
  - `feat(llm): add mistral strategy support`
  - `fix(api): handle missing signature headers`
  - `docs(readme): update setup instructions`

### Pull Request Process

1. **Create a feature branch**
2. **Make your changes**
3. **Write tests**
4. **Update documentation**
5. **Run linting and tests**
6. **Create Pull Request**
7. **Request review**
8. **Address feedback**
9. **Merge to main**

## 🚨 Troubleshooting

### Common Issues

**Issue: `buf generate` fails**
```bash
# Solution: Check proto file syntax
buf lint

# Ensure buf is properly installed
buf --version
```

**Issue: Database connection fails**
```bash
# Solution: Check if PostgreSQL is running
docker-compose ps

# Check connection details in .env
nano .env
```

**Issue: gRPC connection refused**
```bash
# Solution: Check if core service is running
docker-compose logs core-service

# Verify ports are correctly mapped
netstat -tuln | grep 50051
```

**Issue: Missing Python dependencies**
```bash
# Solution: Reinstall dependencies
uv sync

# Check Python version
python --version
```

### Debugging Tips

```bash
# Enable debug logging
# In config.py, set logging level to DEBUG

# Check environment variables
docker-compose exec api-gateway env

# Test gRPC connection manually
# Use grpcurl or similar tools
```

## 📚 Learning Resources

### Protocol Buffers and gRPC
- [Protocol Buffers Documentation](https://developers.google.com/protocol-buffers)
- [gRPC Documentation](https://grpc.io/docs/)
- [Buf Documentation](https://buf.build/docs)

### Python Development
- [Python Documentation](https://docs.python.org/3/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://www.sqlalchemy.org/)

### AI and Vector Search
- [LangChain Documentation](https://python.langchain.com/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Mistral AI Documentation](https://docs.mistral.ai/)

### Observability
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)

## 🤝 Community and Support

- **GitHub Issues**: Report bugs and request features
- **Discussions**: Ask questions and share ideas
- **Contributing**: See CONTRIBUTING.md for guidelines

## 📝 License

[This project is licensed under the MIT License](LICENSE).

## 🙏 Acknowledgments

Thank you for contributing to the Aura Platform! Your work helps build a robust ecosystem for autonomous economic negotiations.