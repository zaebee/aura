FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency files
COPY packages/aura-core /app/packages/aura-core
COPY api-gateway/pyproject.toml api-gateway/uv.lock /app/api-gateway/

WORKDIR /app/api-gateway

RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/api-gateway/.venv/bin:$PATH"

COPY api-gateway/src ./src

ENV PYTHONPATH=/app/api-gateway:/app/api-gateway/src:/app/api-gateway/src/proto

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
