.PHONY: lint test test-cov test-verbose build generate push install-dev format test-health

# Makefile for Aura Project
TAG ?= latest
REGISTRY ?= ghcr.io/myuser
PLATFORM ?= linux/amd64

# --- 1. CODE QUALITY ---
lint:
	# Protobuf Lint
	cd proto && buf lint
	# Python Lint
	uv run ruff check core-service/src api-gateway/src
	# Frontend Lint
	# cd frontend && bun run lint

# Run tests
test:
	uv run pytest core-service/tests/ -v

# Run tests with coverage report
test-cov:
	uv run pytest core-service/tests/ -v --cov=core-service/src --cov-report=term-missing

# Run tests with verbose output
test-verbose:
	uv run pytest core-service/tests/ -vv -s

# Test health endpoints
test-health:
	# Test health check endpoints (requires running services)
	uv run python test_health_endpoints.py

# --- 2. BUILD ---
build: generate
	# Build Docker images for all services
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-gateway:$(TAG) -f api-gateway/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-core:$(TAG) -f core-service/Dockerfile .
	docker build --platform $(PLATFORM) -t $(REGISTRY)/aura-frontend:$(TAG) -f frontend/Dockerfile frontend/

# --- 3. HELPER ---
generate:
	# Generate Protobuf code
	buf generate

# --- 4. PUBLISH (CI ONLY) ---
push:
	# Push Docker images to registry
	docker push $(REGISTRY)/aura-gateway:$(TAG)
	docker push $(REGISTRY)/aura-core:$(TAG)
	docker push $(REGISTRY)/aura-frontend:$(TAG)

# --- 5. DEV TASKS ---
install-dev:
	# Install development dependencies
	uv sync --group dev

format:
	# Format code
	uv run ruff format .
