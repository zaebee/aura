FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install curl and download grpc_health_probe for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL -o /bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.44/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency files
COPY pyproject.toml /app/
COPY packages/aura-core /app/packages/aura-core
COPY core/pyproject.toml core/uv.lock /app/core/

WORKDIR /app/core

RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/core/.venv/bin:$PATH"

# Verify critical packages installed
RUN python -c "import grpc_health.v1.health_pb2"

COPY core/src ./src

COPY core/alembic.ini .
COPY core/migrations ./migrations

# Copy the compiled brain (aura_brain.json) and training data
COPY core/data ./data
COPY core/train_dspy.py .

ENV PYTHONPATH=/app/core:/app/core/src:/app/core/src/hive/proto

EXPOSE 50051
EXPOSE 9091

CMD ["python", "src/main.py"]
