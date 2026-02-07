.PHONY: lint test test-cov test-verbose build generate push install-dev format test-health

# Makefile for Aura Project
TAG ?= latest
REGISTRY ?= ghcr.io/zaebee
PLATFORM ?= linux/amd64
CORE_PATH ?= core:core/src
GATEWAY_PATH ?= api-gateway/src
TG_PATH ?= synapses/telegram-bot/src:synapses/telegram-bot/src/proto
KEEPER_PATH ?= agents/bee-keeper/src

# --- 1. CODE QUALITY ---
lint:
	# Protobuf Lint
	cd proto && buf lint
	# Python Lint (Ruff)
	uv run ruff check .
	# Python Type Check (Mypy)
	MYPYPATH=$(CORE_PATH) uv run mypy core/src
	MYPYPATH=$(GATEWAY_PATH):packages/aura-core/src uv run mypy api-gateway/src
	MYPYPATH=$(TG_PATH):packages/aura-core/src uv run mypy synapses/telegram-bot/src
	MYPYPATH=$(KEEPER_PATH):packages/aura-core/src uv run mypy agents/bee-keeper/main.py agents/bee-keeper/src
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
	PYTHONPATH=$(CORE_PATH) uv run pytest core/tests/ -v
	# Run telegram-bot tests with isolated path to avoid 'src' collision
	PYTHONPATH=$(TG_PATH) uv run pytest synapses/telegram-bot/tests/ -v

# Run tests with coverage report
test-cov:
	PYTHONPATH=$(CORE_PATH) uv run pytest core/tests/ -v --cov=core/src --cov-report=term-missing

# Run tests with verbose output
test-verbose:
	PYTHONPATH=$(CORE_PATH) uv run pytest core/tests/ -vv -s

# --- 2. BUILD ---
build: generate build-tg
	# Build Docker images for all services
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-gateway:$(TAG) -f api-gateway/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-core:$(TAG) -f core/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-frontend:$(TAG) -f frontend/Dockerfile .

build-tg:
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-telegram-bot:$(TAG) -f synapses/telegram-bot/Dockerfile .

# --- 3. HELPER ---
generate:
	# Generate Protobuf code directly into packages/aura-core/src/aura_core/gen/
	# Uses buf.gen.yaml which leverages betterproto
	mkdir -p packages/aura-core/src/aura_core/gen
	buf generate
	# Fix betterproto google import shim if needed
	if [ -d "packages/aura-core/src/aura_core/gen/aura/dna" ]; then \
		mkdir -p packages/aura-core/src/aura_core/gen/aura/dna/google; \
		echo "from betterproto.lib.google import protobuf" > packages/aura-core/src/aura_core/gen/aura/dna/google/__init__.py; \
	fi

# --- 4. PUBLISH (CI ONLY) ---
push: push-tg
	# Push Docker images to registry
	docker push $(REGISTRY)/aura-gateway:$(TAG)
	docker push $(REGISTRY)/aura-core:$(TAG)
	docker push $(REGISTRY)/aura-frontend:$(TAG)

push-tg:
	docker push $(REGISTRY)/aura-telegram-bot:$(TAG)

# --- 5. DEV TASKS ---
install-dev:
	# Install development dependencies
	uv sync --group dev

format:
	# Format code
	uv run ruff format .

# --- 6. CORE TASKS ---
core-seed:
	# Seed the database with initial inventory
	PYTHONPATH=$(CORE_PATH) uv run python core/scripts/seed.py

core-pulse:
	# Trigger a manual NegotiationAccepted event
	PYTHONPATH=$(CORE_PATH) uv run python core/scripts/trigger_pulse.py

core-train:
	# Train the DSPy negotiation engine
	PYTHONPATH=$(CORE_PATH) uv run python core/scripts/training/train_dspy.py

# Test health endpoints
tools-health:
	# Test health check endpoints (requires running services)
	PYTHONPATH=.:$(CORE_PATH) uv run python tools/test_health_endpoints.py

tools-simulate:
	# Run agent negotiation simulation
	PYTHONPATH=:.$(CORE_PATH) uv run python tools/simulators/agent_sim.py

tools-buyer:
	# Run agent negotiation simulation
	PYTHONPATH=:.$(CORE_PATH) uv run python tools/simulators/autonomous_buyer.py
