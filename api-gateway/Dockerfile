FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock /app/
COPY packages/aura-core /app/packages/aura-core
COPY api-gateway/pyproject.toml /app/api-gateway/

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

# Copy source code to the same relative path as builder
COPY api-gateway/src /app/api-gateway/src

WORKDIR /app/api-gateway

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/api-gateway/src:/app/api-gateway/src/proto

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
