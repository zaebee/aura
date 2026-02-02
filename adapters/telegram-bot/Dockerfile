FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace dependency files
COPY pyproject.toml uv.lock README.md ./
COPY packages/aura-core/pyproject.toml ./packages/aura-core/
COPY core-service/pyproject.toml ./core-service/
COPY api-gateway/pyproject.toml ./api-gateway/
COPY adapters/telegram-bot/pyproject.toml ./adapters/telegram-bot/
COPY adapters/mcp-server/pyproject.toml ./adapters/mcp-server/
COPY agents/bee-keeper/pyproject.toml ./agents/bee-keeper/

# Copy the shared package code
COPY packages/aura-core ./packages/aura-core

# Install dependencies (including dev for grpcio-tools)
RUN uv sync --frozen --no-install-project --group dev --package telegram-bot

# Copy proto definitions
COPY proto/ /app/proto/

# Generate gRPC stubs
RUN mkdir -p /app/src/proto && \
    uv run python -m grpc_tools.protoc -I /app/proto \
    --python_out=/app/src/proto \
    --grpc_python_out=/app/src/proto \
    --pyi_out=/app/src/proto \
    /app/proto/aura/negotiation/v1/negotiation.proto

# Final stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace dependency files
COPY pyproject.toml uv.lock README.md ./
COPY packages/aura-core/pyproject.toml ./packages/aura-core/
COPY core-service/pyproject.toml ./core-service/
COPY api-gateway/pyproject.toml ./api-gateway/
COPY adapters/telegram-bot/pyproject.toml ./adapters/telegram-bot/
COPY adapters/mcp-server/pyproject.toml ./adapters/mcp-server/
COPY agents/bee-keeper/pyproject.toml ./agents/bee-keeper/

# Copy the shared package code
COPY packages/aura-core ./packages/aura-core

# Install only production dependencies
RUN uv sync --frozen --no-install-project --package telegram-bot

# Copy generated proto stubs
COPY --from=builder /app/src/proto/ /app/src/proto/

# Copy source code
COPY adapters/telegram-bot/src/ /app/src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app:/app/src:/app/src/proto

# Command to run the bot
CMD ["python", "src/main.py"]
