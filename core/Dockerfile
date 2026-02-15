FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install system dependencies for health probe and health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL -o /bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.44/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe && \
    rm -rf /var/lib/apt/lists/*

# Install buf
RUN BUF_VERSION="1.47.2" && \
    curl -sSL "https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}/buf-Linux-x86_64" -o "/usr/local/bin/buf" && \
    chmod +x "/usr/local/bin/buf"

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock buf.yaml buf.gen.yaml /app/
COPY proto /app/proto
COPY packages/aura-core /app/packages/aura-core
COPY core/pyproject.toml /app/core/
COPY api-gateway/pyproject.toml /app/api-gateway/
COPY synapses/telegram-bot/pyproject.toml /app/synapses/telegram-bot/
COPY synapses/mcp-server/pyproject.toml /app/synapses/mcp-server/
COPY agents/bee-keeper/pyproject.toml /app/agents/bee-keeper/

# Generate Protobuf code
RUN buf generate && \
    # Fix betterproto google import shim
    if [ -d "packages/aura-core/src/aura/dna" ]; then \
        mkdir -p packages/aura-core/src/aura/dna/google; \
        echo "from betterproto.lib.google import protobuf" > packages/aura-core/src/aura/dna/google/__init__.py; \
    fi

# Install dependencies non-editable and scoped to the package, without installing the project itself
RUN uv sync --frozen --no-dev --no-editable --package core --no-install-project

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy grpc_health_probe from builder
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code, generated proto stubs and other artifacts
COPY core/src /app/core/src
COPY --from=builder /app/core/gen-proto /app/core/gen-proto
COPY core/alembic.ini /app/core/alembic.ini
COPY core/migrations /app/core/migrations
COPY core/data /app/core/data

WORKDIR /app/core

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/core/src:/app/core/gen-proto

# Verify critical packages installed
RUN python -c "import grpc_health.v1.health_pb2"

EXPOSE 50051
EXPOSE 9091

CMD ["python", "src/main.py"]
