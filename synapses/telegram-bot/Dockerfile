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
COPY core /app/core
COPY synapses/telegram-bot/pyproject.toml /app/synapses/telegram-bot/

# Generate Protobuf code
RUN buf generate && \
    # Fix betterproto google import shim
    if [ -d "packages/aura-core/src/aura_core/gen/aura/dna" ]; then \
        mkdir -p packages/aura-core/src/aura_core/gen/aura/dna/google; \
        echo "from betterproto.lib.google import protobuf" > packages/aura-core/src/aura_core/gen/aura/dna/google/__init__.py; \
    fi

# Install dependencies non-editable and scoped to the package, without installing the project itself
RUN uv sync --frozen --no-dev --no-editable --package telegram-bot --no-install-project

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code and generated stubs to the same relative path as builder
COPY synapses/telegram-bot/src /app/synapses/telegram-bot/src
COPY --from=builder /app/synapses/telegram-bot/gen-proto /app/synapses/telegram-bot/gen-proto

WORKDIR /app/synapses/telegram-bot

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/synapses/telegram-bot/src:/app/synapses/telegram-bot/gen-proto

# Command to run the bot
CMD ["python", "src/main.py"]
