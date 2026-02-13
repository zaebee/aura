FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install buf
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    BUF_VERSION="1.47.2" && \
    curl -sSL "https://github.com/bufbuild/buf/releases/download/v${BUF_VERSION}/buf-Linux-x86_64" -o "/usr/local/bin/buf" && \
    chmod +x "/usr/local/bin/buf" && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock buf.yaml buf.gen.yaml /app/
COPY proto /app/proto
COPY packages/aura-core /app/packages/aura-core
COPY api-gateway/pyproject.toml /app/api-gateway/
COPY core/pyproject.toml /app/core/
COPY synapses/telegram-bot/pyproject.toml /app/synapses/telegram-bot/
COPY synapses/mcp-server/pyproject.toml /app/synapses/mcp-server/
COPY agents/bee-keeper/pyproject.toml /app/agents/bee-keeper/

# Generate Protobuf code
RUN buf generate && \
    # Fix betterproto google import shim (Modular DNA)
    find packages/aura-core/src/aura_core/gen -type d -name "google" -exec sh -c 'echo "from betterproto.lib.google import protobuf" > {}/__init__.py' \;

# Install dependencies non-editable and scoped to the package, without installing the project itself
RUN uv sync --frozen --no-dev --no-editable --package api-gateway --no-install-project

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code and generated proto stubs
COPY api-gateway/src /app/api-gateway/src
COPY --from=builder /app/api-gateway/gen-proto /app/api-gateway/gen-proto

WORKDIR /app/api-gateway

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/api-gateway/src:/app/api-gateway/gen-proto

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
