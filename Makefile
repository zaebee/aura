.PHONY: lint test test-cov test-verbose build generate generate-local push install-dev format test-health

# Makefile for Aura Project
TAG ?= latest
REGISTRY ?= ghcr.io/zaebee
PLATFORM ?= linux/amd64
DNA_PATH ?= packages/aura-core/src
CORE_PATH ?= core:core/src:core/gen-proto
GATEWAY_PATH ?= api-gateway/src:api-gateway/gen-proto
TG_PATH ?= synapses/telegram-bot/src:synapses/telegram-bot/gen-proto
MCP_PATH ?= synapses/mcp-server/src:synapses/mcp-server/gen-proto
KEEPER_PATH ?= agents/bee-keeper/src

# --- 1. CODE QUALITY ---
lint:
	# Protobuf Lint (skip if buf not installed)
	@if command -v buf >/dev/null 2>&1; then cd proto && buf lint; else echo "  ⚠ buf not found, skipping proto lint"; fi
	# Python Lint (Ruff)
	PYTHONPATH=$(CORE_PATH):$(GATEWAY_PATH):$(TG_PATH):$(MCP_PATH):$(KEEPER_PATH):$(DNA_PATH) uv run ruff check .
	# Python Type Check (Mypy)
	# We use --explicit-package-bases to avoid double discovery when multiple paths overlap
	MYPYPATH=$(CORE_PATH):$(DNA_PATH) uv run mypy --explicit-package-bases core/src
	MYPYPATH=$(GATEWAY_PATH):packages/aura-core/src uv run mypy --explicit-package-bases api-gateway/src
	MYPYPATH=$(TG_PATH):core/src:core/gen-proto:packages/aura-core/src uv run mypy --explicit-package-bases synapses/telegram-bot/src
	MYPYPATH=$(MCP_PATH):core/src:core/gen-proto:packages/aura-core/src uv run mypy --explicit-package-bases synapses/mcp-server/src
	MYPYPATH=$(KEEPER_PATH):packages/aura-core/src uv run mypy agents/bee-keeper/main.py agents/bee-keeper/src
	MYPYPATH=$(DNA_PATH) uv run mypy packages/aura-core/src
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
	# Run mcp-server tests if they exist
	if [ -d "synapses/mcp-server/tests" ]; then PYTHONPATH=$(MCP_PATH):$(CORE_PATH) uv run pytest synapses/mcp-server/tests/ -v; fi

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
PROTO_DIR   ?= proto
PROTO_SRC   := $(wildcard proto/aura/*/v1/*.proto)
GRPC_TARGETS := core/gen-proto api-gateway/gen-proto synapses/telegram-bot/gen-proto
BETTERPROTO_OUT := packages/aura-core/src/aura_core/gen

# CI-friendly: uses remote buf plugins (requires auth)
generate:
	mkdir -p $(BETTERPROTO_OUT)
	buf generate
	# Fix betterproto google import shim if needed
	@if [ -d "$(BETTERPROTO_OUT)/aura/dna" ]; then \
		mkdir -p $(BETTERPROTO_OUT)/aura/dna/google; \
		echo "from betterproto.lib.google import protobuf" > $(BETTERPROTO_OUT)/aura/dna/google/__init__.py; \
	fi

# Local-friendly: uses grpc_tools.protoc + betterproto (no buf auth needed)
generate-local:
	# --- gRPC Python stubs (protobuf + grpc + pyi) for every service ---
	@for dir in $(GRPC_TARGETS); do \
		mkdir -p $$dir; \
		uv run python -m grpc_tools.protoc \
			-I $(PROTO_DIR) \
			--python_out=$$dir \
			--grpc_python_out=$$dir \
			--pyi_out=$$dir \
			$(PROTO_SRC); \
		echo "  ✓ $$dir"; \
	done
	# --- Betterproto Pydantic models (aura-core DNA) ---
	mkdir -p $(BETTERPROTO_OUT)
	uv run python -m grpc_tools.protoc \
		-I $(PROTO_DIR) \
		--python_betterproto_out=$(BETTERPROTO_OUT) \
		$(PROTO_SRC)
	@echo "  ✓ $(BETTERPROTO_OUT)"
	# Fix betterproto google import shim if needed
	@if [ -d "$(BETTERPROTO_OUT)/aura/dna" ]; then \
		mkdir -p $(BETTERPROTO_OUT)/aura/dna/google; \
		echo "from betterproto.lib.google import protobuf" > $(BETTERPROTO_OUT)/aura/dna/google/__init__.py; \
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
	PYTHONPATH=$(CORE_PATH) uv run python tools/test_health_endpoints.py

tools-distill:
	# Distill architectural knowledge from the codebase into binary/JSON artifacts
	PYTHONPATH=$(CORE_PATH) uv run python tools/distill_knowledge.py

tools-validate:
	# Validate knowledge artifacts against the markdown architectural anchor
	PYTHONPATH=$(CORE_PATH) uv run python tools/validate_knowledge.py

tools-simulate:
	# Run agent negotiation simulation
	PYTHONPATH=$(CORE_PATH) uv run python tools/simulators/agent_sim.py

tools-buyer:
	# Run agent negotiation simulation
	PYTHONPATH=$(CORE_PATH) uv run python tools/simulators/autonomous_buyer.py
