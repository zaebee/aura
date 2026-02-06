# Aura Platform Signal Map (Environment Variables)

This document serves as the single source of truth for all environment variables used across the Aura platform.

## Global Standards

- **Prefix:** `AURA_`
- **Nested Delimiter:** `__` (double underscore)
- **Convention:** Pydantic `BaseSettings` validation is enforced. Required fields without defaults will cause the service to fail-fast at startup if missing.

---

## 1. Core Service (`core`)

| Variable | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| `AURA_SERVER__PORT` | `int` | No | `50051` | gRPC server port |
| `AURA_SERVER__LOG_LEVEL` | `str` | No | `info` | Logging verbosity |
| `AURA_SERVER__NATS_URL` | `str` | **Yes** | - | NATS connection URL |
| `AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT` | `str` | No | `http://localhost:4317` | OpenTelemetry collector endpoint |
| `AURA_DATABASE__URL` | `str` | **Yes** | - | PostgreSQL connection string |
| `AURA_DATABASE__REDIS_URL` | `str` | **Yes** | - | Redis connection string |
| `AURA_LLM__MODEL` | `str` | No | `mistral/mistral-large-latest` | LLM model identifier |
| `AURA_LLM__API_KEY` | `Secret` | **Yes** | - | Primary LLM API Key (Mistral/OpenAI) |
| `AURA_LLM__OPENAI_API_KEY` | `Secret` | No | - | Optional secondary OpenAI key |
| `AURA_CRYPTO__ENABLED` | `bool` | No | `false` | Enable/Disable crypto payments |
| `AURA_CRYPTO__SOLANA_PRIVATE_KEY` | `Secret` | No | - | Platform Solana wallet key |
| `AURA_CRYPTO__SECRET_ENCRYPTION_KEY` | `Secret` | No | - | Key for encrypting deal secrets |

## 2. API Gateway (`gateway`)

| Variable | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| `AURA_GATEWAY__CORE_SERVICE_HOST` | `str` | **Yes** | - | Core gRPC endpoint (FQDN) |
| `AURA_GATEWAY__LOG_LEVEL` | `str` | No | `info` | Logging verbosity |
| `AURA_GATEWAY__CORS_ORIGINS` | `str` | No | `*` | Allowed CORS origins (comma-sep) |
| `AURA_GATEWAY__OTEL_EXPORTER_OTLP_ENDPOINT` | `str` | No | - | OpenTelemetry collector endpoint |

## 3. Telegram Bot (`tg`)

| Variable | Type | Required | Default | Description |
| :--- | :--- | :---: | :--- | :--- |
| `AURA_TG__TOKEN` | `Secret` | **Yes** | - | Telegram Bot API Token |
| `AURA_TG__CORE_URL` | `str` | **Yes** | - | Core gRPC endpoint (FQDN) |
| `AURA_TG__NATS_URL` | `str` | **Yes** | - | NATS connection URL |
| `AURA_TG__LOG_LEVEL` | `str` | No | `info` | Logging verbosity |

---

## Kubernetes Secret Mapping

The CI/CD pipeline maps GitHub Secrets to a unified Kubernetes secret named `aura-secrets`.

| K8s Secret Key | Source (GitHub Secret) | Used By |
| :--- | :--- | :--- |
| `telegram-token` | `AURA_TELEGRAM_TOKEN` | `telegram-bot` |
| `api-key` | `MISTRAL_API_KEY` | `core` |
| `openai-key` | `OPENAI_API_KEY` | `core` |
| `secret-encryption-key` | `AURA_SECRET_ENCRYPTION_KEY` | `core` |
| `frp-client-token` | `FRP_CLIENT_TOKEN` | `tunnel` |
| `solana-private-key` | `SOLANA_PRIVATE_KEY` | `core` |
