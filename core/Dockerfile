FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install system dependencies for health probe and health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL -o /bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.44/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock /app/
COPY packages/aura-core /app/packages/aura-core
COPY core/pyproject.toml /app/core/

# Install dependencies non-editable and scoped to the package, without installing the project itself
RUN uv sync --frozen --no-dev --no-editable --package core --no-install-project

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy grpc_health_probe from builder
COPY --from=builder /bin/grpc_health_probe /bin/grpc_health_probe

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code and other artifacts to the same relative path as builder
COPY core/src /app/core/src
COPY core/alembic.ini /app/core/alembic.ini
COPY core/migrations /app/core/migrations
COPY core/data /app/core/data
# COPY core/scripts/training/train_dspy.py /app/core/train_dspy.py

WORKDIR /app/core

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/core:/app/core/src:/app/core/src/hive/proto

# Verify critical packages installed
RUN python -c "import grpc_health.v1.health_pb2"

EXPOSE 50051
EXPOSE 9091

CMD ["python", "src/main.py"]
