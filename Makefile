.PHONY: lint test test-cov test-verbose build generate push install-dev format test-health

# Makefile for Aura Project
TAG ?= latest
REGISTRY ?= ghcr.io/zaebee
PLATFORM ?= linux/amd64

# --- 1. CODE QUALITY ---
lint:
	# Protobuf Lint
	cd proto && buf lint
	# Python Lint (Ruff)
	uv run ruff check .
	# Python Type Check (Mypy)
	MYPYPATH=core/src:packages/aura-core/src uv run mypy core/src
	MYPYPATH=api-gateway/src:packages/aura-core/src uv run mypy api-gateway/src
	MYPYPATH=adapters/telegram-bot/src:adapters/telegram-bot/src/proto:packages/aura-core/src uv run mypy adapters/telegram-bot/src
	MYPYPATH=agents/bee-keeper/src:packages/aura-core/src uv run mypy agents/bee-keeper/main.py agents/bee-keeper/src
	MYPYPATH=packages/aura-core/src uv run mypy packages/aura-core/src
	# Security Audit (Bandit)
	uv run bandit -r . -c pyproject.toml
	# Frontend Lint
	# cd frontend && bun run lint

setup-hooks:
	# Install pre-commit hooks
	uv run pre-commit install

# Run tests
test:
	# Run core tests
	PYTHONPATH=core:core/src uv run pytest core/tests/ -v
	# Run telegram-bot tests with isolated path to avoid 'src' collision
	PYTHONPATH=adapters/telegram-bot/src:adapters/telegram-bot/src/proto uv run pytest adapters/telegram-bot/tests/ -v

# Run tests with coverage report
test-cov:
	PYTHONPATH=core:core/src uv run pytest core/tests/ -v --cov=core/src --cov-report=term-missing

# Run tests with verbose output
test-verbose:
	PYTHONPATH=core:core/src uv run pytest core/tests/ -vv -s

# Test health endpoints
test-health:
	# Test health check endpoints (requires running services)
	uv run python tools/test_health_endpoints.py

simulate:
	# Run agent negotiation simulation
	uv run python tools/simulators/agent_sim.py


telemetry:
	# Trigger a manual NegotiationAccepted event
	PYTHONPATH=core:core/src uv run python core/scripts/trigger_pulse.py

# --- 2. BUILD ---
build: generate build-tg
	# Build Docker images for all services
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-gateway:$(TAG) -f api-gateway/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-core:$(TAG) -f core/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-frontend:$(TAG) -f frontend/Dockerfile .

build-tg:
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-telegram-bot:$(TAG) -f adapters/telegram-bot/Dockerfile .

# --- 3. HELPER ---
generate:
	# Generate Protobuf code
	buf generate

# --- 4. PUBLISH (CI ONLY) ---
push: push-tg
	# Push Docker images to registry
	docker push $(REGISTRY)/aura-gateway:$(TAG)
	docker push $(REGISTRY)/aura-core:$(TAG)
	docker push $(REGISTRY)/aura-frontend:$(TAG)

push-tg:
	docker push $(REGISTRY)/aura-telegram-bot:$(TAG)

# --- 5. DEV TASKS ---
seed:
	# Seed the database with initial inventory
	PYTHONPATH=core:core/src uv run python core/scripts/seed.py

train:
	# Train the DSPy negotiation engine
	PYTHONPATH=core:core/src uv run python core/scripts/training/train_dspy.py

pulse:
	# Trigger a manual NegotiationAccepted event
	PYTHONPATH=core:core/src uv run python core/scripts/trigger_pulse.py

install-dev:
	# Install development dependencies
	uv sync --group dev

format:
	# Format code
	uv run ruff format .
