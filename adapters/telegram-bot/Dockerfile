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

# Copy dependency files
COPY adapters/telegram-bot/pyproject.toml adapters/telegram-bot/uv.lock ./

# Install dependencies (including dev for grpcio-tools)
RUN uv sync --frozen --no-install-project --group dev

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

# Copy dependency files
COPY adapters/telegram-bot/pyproject.toml adapters/telegram-bot/uv.lock ./

# Install only production dependencies
RUN uv sync --frozen --no-install-project

# Copy generated proto stubs
COPY --from=builder /app/src/proto/ /app/src/proto/

# Copy source code
COPY adapters/telegram-bot/src/ /app/src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app:/app/src:/app/src/proto

# Command to run the bot
CMD ["python", "src/main.py"]
