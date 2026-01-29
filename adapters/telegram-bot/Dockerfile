FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv --link
ENV PATH="/app/.venv/bin:$PATH"
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
FROM python:3.12-slim

WORKDIR /app

# Copy virtual env from builder stage (only runtime deps)
# We need to sync again without dev to keep the image small,
# or just copy the .venv and be aware it has dev deps.
# Actually, let's just use the builder venv for now, but in a real prod we'd prune.
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy generated proto stubs
COPY --from=builder /app/src/proto/ /app/src/proto/

# Copy source code
COPY adapters/telegram-bot/src/ /app/src/

# Set environment variables
ENV PYTHONPATH=/app:/app/src:/app/src/proto

# Command to run the bot
CMD ["python", "src/main.py"]
