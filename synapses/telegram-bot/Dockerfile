FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install uv for dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy workspace and dependency files
COPY pyproject.toml uv.lock /app/
COPY packages/aura-core /app/packages/aura-core
COPY synapses/telegram-bot/pyproject.toml /app/synapses/telegram-bot/

# Install dependencies scoped to telegram-bot (no core needed — communicates via NATS)
RUN uv sync --frozen --no-dev --no-install-project --no-editable --package telegram-bot

# Final stage
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy virtual environment from builder (workspace root .venv)
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY synapses/telegram-bot/src /app/synapses/telegram-bot/src

WORKDIR /app/synapses/telegram-bot

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/synapses/telegram-bot/src

EXPOSE 8080

# Command to run the bot
CMD ["python", "src/main.py"]
