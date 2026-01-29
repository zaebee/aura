FROM python:3.11-slim as builder

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

# Install dependencies (including grpcio-tools for generation)
# We need to install dev dependencies in builder to have grpcio-tools
RUN uv sync --frozen --no-install-project

# Copy proto definitions
COPY proto/ /app/proto/

# Generate gRPC stubs into /app/generated
RUN mkdir /app/generated && \
    uv run python -m grpc_tools.protoc -I /app/proto \
    --python_out=/app/generated \
    --grpc_python_out=/app/generated \
    --pyi_out=/app/generated \
    /app/proto/aura/negotiation/v1/negotiation.proto

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy virtual env from builder stage (only runtime deps)
# Actually, builder has dev deps. Let's do a cleaner approach for runtime.
# But for now, let's just copy the .venv.
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy generated proto stubs
COPY --from=builder /app/generated/ /app/src/proto/

# Copy source code
COPY adapters/telegram-bot/src/ /app/src/

# Set environment variables
ENV PYTHONPATH=/app:/app/src:/app/src/proto

# Command to run the bot
CMD ["python", "src/main.py"]
