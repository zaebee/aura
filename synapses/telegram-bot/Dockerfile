FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock /app/
COPY packages/aura-core /app/packages/aura-core
COPY synapses/telegram-bot/pyproject.toml /app/synapses/telegram-bot/

# Install dependencies including dev for stub generation, scoped to telegram-bot
RUN uv sync --frozen --no-install-project --group dev --package telegram-bot

# Copy proto definitions (needed for stub generation)
COPY proto/ /app/proto/

# Generate gRPC stubs
RUN mkdir -p /app/synapses/telegram-bot/src/proto && \
    uv run python -m grpc_tools.protoc -I /app/proto \
    --python_out=/app/synapses/telegram-bot/src/proto \
    --grpc_python_out=/app/synapses/telegram-bot/src/proto \
    --pyi_out=/app/synapses/telegram-bot/src/proto \
    /app/proto/aura/negotiation/v1/negotiation.proto

# Final sync for production (no-dev, no-editable, scoped to package)
RUN uv sync --frozen --no-dev --no-install-project --no-editable --package telegram-bot

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code and generated stubs to the same relative path as builder
COPY synapses/telegram-bot/src /app/synapses/telegram-bot/src
COPY --from=builder /app/synapses/telegram-bot/src/proto /app/synapses/telegram-bot/src/proto

WORKDIR /app/synapses/telegram-bot

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/synapses/telegram-bot/src:/app/synapses/telegram-bot/src/proto

# Command to run the bot
CMD ["python", "src/main.py"]
