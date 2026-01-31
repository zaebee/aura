# bee.Keeper Agent

The guardian of the Aura Hive. An autonomous agent that monitors repository health, consistency with ATCG patterns, and provides "Honey-Aware" feedback.

## Agent DNA

The `bee.Keeper` follows the **ATCG** (Aggregator, Transformer, Connector, Generator) pattern:

- **A - Aggregator**: Gathers "Signals" from the environment.
  - `get_git_diff()`: Current PR or last commit changes.
  - `get_hive_metrics()`: Queries Prometheus for negotiation success rates.
  - `scan_filesystem()`: Maps the current directory structure.
- **T - Transformer**: The "Inquisitor" brain.
  - Analyzes git diffs for architectural "Heresies".
  - Enforces the use of `structlog` and `settings`.
  - Verifies compliance with `dna.py` Protocols.
- **C - Connector**: The "Hand" that interacts with the world.
  - Posts "Purity Reports" to GitHub.
  - Emits NATS events to notify the Hive of audit completion.
- **G - Generator**: The "Scribe".
  - Synchronizes `llms.txt` if Protobuf definitions change.
  - Updates `CHRONICLES.md` with narrative audit results.

## Frugal Mind

The agent is designed to be cost-effective:
- Defaults to "cheap" models (e.g., `gpt-4o-mini`).
- Includes fallback logic to local Ollama endpoints if budget is tight or primary LLM fails.

## Configuration

Settings are managed via Pydantic and environment variables with the `AURA_` prefix.

| Variable | Description | Default |
|----------|-------------|---------|
| `AURA_LLM__API_KEY` | LLM API Key | required |
| `AURA_LLM__MODEL` | LLM Model | `gpt-4o-mini` |
| `AURA_LLM__FALLBACK_MODEL` | Fallback Model | `ollama/llama3` |
| `AURA_LLM__OLLAMA_BASE_URL` | Ollama URL | `http://localhost:11434` |
| `AURA_PROMETHEUS_URL` | Prometheus URL | `http://prometheus:9090` |
| `AURA_NATS_URL` | NATS URL | `nats://nats:4222` |
