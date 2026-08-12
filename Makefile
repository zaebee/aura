.PHONY: lint mypy test test-cov test-verbose build generate push install-dev format test-health keeper-audit \
       run-core run-gateway run-frontend prepare-bun

# Makefile for Aura Project
TAG ?= latest
REGISTRY ?= ghcr.io/zaebee
PLATFORM ?= linux/amd64
DNA_PATH := packages/aura-core/src:packages/aura-core/gen-proto
CORE_PATH := core/src:core/gen-proto:$(DNA_PATH)
GATEWAY_PATH := api-gateway/src:api-gateway/gen-proto:$(DNA_PATH)
TG_PATH := synapses/telegram-bot/src:$(DNA_PATH)
MCP_PATH := synapses/mcp-server/src:synapses/mcp-server/gen-proto:core/src:$(DNA_PATH)
KEEPER_PATH := agents/bee-keeper/src:$(DNA_PATH)
TOOL_PATH := $(CORE_PATH):$(DNA_PATH)

# Proto source files (for incremental generation)
PROTO_SOURCES := $(wildcard proto/aura/*/v1/*.proto)
PROTO_SENTINEL := .gen-proto.stamp

# --- 1. CODE QUALITY ---
lint: $(PROTO_SENTINEL)
	# Protobuf Lint
	cd proto && buf lint
	# Python Lint (Ruff)
	PYTHONPATH=$(DNA_PATH):$(CORE_PATH):$(GATEWAY_PATH):$(TG_PATH):$(MCP_PATH):$(KEEPER_PATH) uv run ruff check .
	# Formatting is checked, not merely applied by whoever ran `make format` last.
	# Without this the repo does not verify the format it claims to enforce, and
	# a file's formatting is whatever tool touched it most recently.
	uv run ruff format --check .
	# Python Type Check (Mypy)
	# We use --explicit-package-bases to avoid double discovery when multiple paths overlap
	MYPYPATH=$(CORE_PATH) uv run mypy --explicit-package-bases core/src
	MYPYPATH=$(GATEWAY_PATH) uv run mypy --explicit-package-bases api-gateway/src
	MYPYPATH=$(TG_PATH) uv run mypy --explicit-package-bases synapses/telegram-bot/src
	MYPYPATH=$(MCP_PATH) uv run mypy --explicit-package-bases synapses/mcp-server/src
	MYPYPATH=$(KEEPER_PATH) uv run mypy --explicit-package-bases agents/bee-keeper/src
	MYPYPATH=$(DNA_PATH) uv run mypy packages/aura-core/src
	# Security Audit (Bandit)
	uv run bandit -r . -c pyproject.toml
	# Fractal Completeness (ATCG-M baseline-lock gate)
	uv run python tools/check_fractal_completeness.py
	# Frontend Lint
	# cd frontend && bun run lint

mypy:
	MYPYPATH=$(CORE_PATH) uv run mypy --explicit-package-bases core/src
	MYPYPATH=$(GATEWAY_PATH) uv run mypy --explicit-package-bases api-gateway/src
	MYPYPATH=$(TG_PATH) uv run mypy --explicit-package-bases synapses/telegram-bot/src
	MYPYPATH=$(MCP_PATH) uv run mypy --explicit-package-bases synapses/mcp-server/src
	MYPYPATH=$(KEEPER_PATH) uv run mypy --explicit-package-bases agents/bee-keeper/src
	MYPYPATH=$(DNA_PATH) uv run mypy packages/aura-core/src

setup-hooks:
	# Install pre-commit hooks
	uv run pre-commit install

# Run tests
keeper-audit: $(PROTO_SENTINEL)
	# One bee.Keeper cycle, then exit. Without --once main.py is a NATS daemon.
	PYTHONPATH=$(KEEPER_PATH) uv run python -m aura_keeper.main --once

test: $(PROTO_SENTINEL)
	# Run core tests
	PYTHONPATH=$(CORE_PATH) uv run pytest core/tests/ -v
	# Run api-gateway tests (env is provided by api-gateway/tests/conftest.py).
	# Sync the gateway's own declared deps rather than trusting the root env to
	# happen to carry them: it is a workspace member, not a root dependency, so
	# `uv sync --group dev` never reaches its declarations, and until something
	# else stopped pulling python-multipart in nobody could tell. --inexact adds
	# them to what is already synced; --no-sync stops `uv run` reverting that.
	uv sync --package api-gateway --inexact
	PYTHONPATH=$(GATEWAY_PATH) uv run --no-sync pytest api-gateway/tests/ -v
	# Run telegram-bot tests with isolated path to avoid 'src' collision
	PYTHONPATH=$(TG_PATH) uv run pytest synapses/telegram-bot/tests/ -v
	# Run bee.Keeper tests from the root env: its transformer imports dspy, which
	# is declared in the root pyproject rather than the agent's own.
	PYTHONPATH=$(KEEPER_PATH) uv run pytest agents/bee-keeper/tests/ -v
	# Run bee.Evolver tests in its own env — it deliberately has no aura-core dep.
	cd agents/bee-evolver && uv run --group dev pytest tests/ -v
	# Run the aura-core packaging guard: it builds the wheel in place and asserts
	# the hook-generated aura_core_gen actually lands in it. No PYTHONPATH — the
	# guard inspects the built artifact, it never imports aura_core.
	uv run pytest packages/aura-core/tests/ -v
	# Run mcp-server tests if they exist.
	# aura-mcp's runtime deps (fastmcp) aren't in the root dev group, so add them
	# additively (--inexact keeps the already-synced dev deps, avoids aura-worker's
	# heavy torch stack); --no-sync stops `uv run` from reverting that.
	if [ -d "synapses/mcp-server/tests" ]; then \
		uv sync --package aura-mcp --inexact; \
		PYTHONPATH=$(MCP_PATH):$(CORE_PATH) uv run --no-sync pytest synapses/mcp-server/tests/ -v; \
	fi
	# Run aura-worker tests if they exist. Its runtime deps (gradio) aren't in
	# the root dev group; add them additively (--inexact). The `ml` group with
	# torch is NOT synced, so no heavy CUDA stack; --no-sync keeps the install.
	if [ -d "packages/aura-worker/tests" ]; then \
		uv sync --package aura-worker --inexact; \
		PYTHONPATH=packages/aura-worker/src:$(DNA_PATH) uv run --no-sync pytest packages/aura-worker/tests/ -v; \
	fi

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

# Incremental generation: only re-run buf if .proto files changed
$(PROTO_SENTINEL): $(PROTO_SOURCES) buf.gen.yaml
	# Generate Protobuf code directly into packages/aura-core/gen-proto/aura_core_gen
	# Uses buf.gen.yaml which leverages betterproto
	mkdir -p packages/aura-core/gen-proto/aura_core_gen
	buf generate
	# Fix betterproto google import shim
	if [ -d "packages/aura-core/gen-proto/aura_core_gen/aura/core" ]; then \
		mkdir -p packages/aura-core/gen-proto/aura_core_gen/aura/core/google; \
		echo "from betterproto.lib.google import protobuf" > packages/aura-core/gen-proto/aura_core_gen/aura/core/google/__init__.py; \
	fi
	# Post-generation fix for double-prefix in negotiation chromosome
	if [ -f "packages/aura-core/gen-proto/aura_core_gen/aura/negotiation/v1.py" ]; then \
		sed -i 's/from \.aura\.core import v1/from aura_core_gen.aura.core import v1/g' packages/aura-core/gen-proto/aura_core_gen/aura/negotiation/v1.py; \
	fi
	if [ -d "packages/aura-core/gen-proto/aura_core_gen/aura/assets" ]; then \
		mkdir -p packages/aura-core/gen-proto/aura_core_gen/aura/assets/google; \
		echo "from betterproto.lib.google import protobuf" > packages/aura-core/gen-proto/aura_core_gen/aura/assets/google/__init__.py; \
	fi
	touch $(PROTO_SENTINEL)

generate: $(PROTO_SENTINEL)

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

# --- 6. RUN SERVICES (auto-generates protos if needed) ---
run-core: $(PROTO_SENTINEL)
	# Run Core gRPC service
	PYTHONPATH=$(TOOL_PATH) uv run python -m aura_hive.main

run-gateway: $(PROTO_SENTINEL)
	# Run API Gateway
	PYTHONPATH=$(GATEWAY_PATH):$(DNA_PATH) uv run uvicorn api_gateway.main:app --host 0.0.0.0 --port 8000 --app-dir api-gateway/src

prepare-bun:
	# Install frontend dependencies via bun
	cd frontend && bun install

run-frontend: prepare-bun
	# Run Frontend dev server
	cd frontend && bun run dev

# --- 7. CORE TASKS ---
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
	PYTHONPATH=$(TOOL_PATH) uv run python tools/test_health_endpoints.py

tools-distill:
	# Distill architectural knowledge from the codebase into binary/JSON artifacts
	PYTHONPATH=$(TOOL_PATH) uv run python tools/distill_knowledge.py

tools-validate:
	# Validate knowledge artifacts against the markdown architectural anchor
	PYTHONPATH=$(TOOL_PATH) uv run python tools/validate_knowledge.py

tools-simulate:
	# Run agent negotiation simulation
	PYTHONPATH=$(TOOL_PATH) uv run python tools/simulators/agent_sim.py

tools-buyer:
	# Run agent negotiation simulation
	PYTHONPATH=$(TOOL_PATH) uv run python tools/simulators/autonomous_buyer.py

verify-receipts:
	# Check the receipts a running Hive left in its log (LOG=path, or stdin when unset)
	PYTHONPATH=$(TOOL_PATH):. uv run python tools/verify_receipts.py $(LOG)

resolve-dispute:
	# Resolve a dispute token into the receipt it names (TOKEN=<uuid>)
	PYTHONPATH=$(TOOL_PATH):$(CORE_PATH) uv run python tools/resolve_dispute.py $(TOKEN)
