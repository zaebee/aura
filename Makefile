.PHONY: test test-cov test-verbose install-dev lint format

# Run all tests
test:
	uv run pytest core-service/tests/ -v

# Run tests with coverage report
test-cov:
	uv run pytest core-service/tests/ -v --cov=core-service/src --cov-report=term-missing

# Run tests with verbose output
test-verbose:
	uv run pytest core-service/tests/ -vv -s

# Install development dependencies
install-dev:
	uv sync --group dev

# Run linter
lint:
	uv run ruff check .

# Format code
format:
	uv run ruff format .
