FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
# Copy all pyproject.toml files to satisfy workspace requirements
COPY packages/aura-core/pyproject.toml ./packages/aura-core/
COPY core-service/pyproject.toml ./core-service/
COPY api-gateway/pyproject.toml ./api-gateway/
COPY adapters/telegram-bot/pyproject.toml ./adapters/telegram-bot/
COPY adapters/mcp-server/pyproject.toml ./adapters/mcp-server/
COPY agents/bee-keeper/pyproject.toml ./agents/bee-keeper/

# Copy the shared package code
COPY packages/aura-core ./packages/aura-core

RUN uv sync --frozen --no-dev --no-install-project --package api-gateway

ENV PATH="/app/.venv/bin:$PATH"

COPY api-gateway/src ./src

ENV PYTHONPATH=/app:/app/src:/app/src/proto

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]