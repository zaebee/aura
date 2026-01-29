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

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

# Verify critical packages installed
RUN python -c "import grpc_health.v1.health_pb2"

COPY core-service/src ./src

COPY core-service/alembic.ini .
COPY core-service/migrations ./migrations

ENV PYTHONPATH=/app:/app/src:/app/src/proto

EXPOSE 50051
EXPOSE 9091

CMD ["python", "src/main.py"]
