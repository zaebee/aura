# Environment Variable Signal Map

This document lists all environment variables used across the Aura Hive, their purpose, their service, and their required status.

## Prefix and Delimiter
- **Prefix:** `AURA_`
- **Nested Delimiter:** `__`

## Strict Rule: FQDN for Internal URLs
All internal service-to-service communication must use Full Qualified Domain Names (FQDN) in the format:
`<service-name>.<namespace>.svc.cluster.local`

## Signal Map Table

| Variable | Service | Required | Purpose |
|----------|---------|----------|---------|
| `AURA_DATABASE__URL` | Core | Yes | PostgreSQL connection DSN. Must use FQDN in cluster. |
| `AURA_DATABASE__REDIS_URL` | Core | Yes | Redis connection DSN. Must use FQDN in cluster. |
| `AURA_DATABASE__VECTOR_DIMENSION` | Core | No | Dimension for vector embeddings (default: 1024). |
| `AURA_LLM__API_KEY` | Core | Yes | API Key for the primary LLM (e.g., Mistral). |
| `AURA_LLM__MODEL` | Core | No | LLM model name (default: mistral/mistral-large-latest). |
| `AURA_LLM__OPENAI_API_KEY` | Core | No | API Key for OpenAI (if using OpenAI models). |
| `AURA_CRYPTO__ENABLED` | Core | No | Toggle for crypto payment features (default: false). |
| `AURA_CRYPTO__SECRET_ENCRYPTION_KEY` | Core | Yes* | Fernet key for encrypting deal secrets. (*Required if enabled) |
| `AURA_CRYPTO__SOLANA_PRIVATE_KEY` | Core | Yes* | Solana private key for payments. (*Required if enabled) |
| `AURA_SERVER__PORT` | Core | No | gRPC server port (default: 50051). |
| `AURA_SERVER__LOG_LEVEL` | Core | No | Logging level (default: info). |
| `AURA_SERVER__NATS_URL` | Core | No | NATS server URL. Must use FQDN in cluster. |
| `AURA_SERVER__PROMETHEUS_URL` | Core | No | Prometheus URL for metrics. (Uses FQDN). |
| `AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT` | Core | No | Jaeger OTLP exporter endpoint. (Uses FQDN). |
| `AURA_GATEWAY__CORE_SERVICE_HOST` | Gateway | Yes | Address of the Core gRPC service. Must use FQDN in cluster. |
| `AURA_GATEWAY__HTTP_PORT` | Gateway | No | HTTP port for the API Gateway (default: 8000). |
| `AURA_GATEWAY__LOG_LEVEL` | Gateway | No | Logging level (default: info). |
| `AURA_GATEWAY__CORS_ORIGINS` | Gateway | No | Allowed CORS origins (comma-separated). |
| `AURA_GATEWAY__OTEL_EXPORTER_OTLP_ENDPOINT` | Gateway | No | Jaeger OTLP exporter endpoint. (Uses FQDN). |
| `AURA_TG__TOKEN` | Telegram | Yes | Telegram Bot Token. |
| `AURA_TG__CORE_URL` | Telegram | Yes | Address of the Core gRPC service. Must use FQDN in cluster. |
| `AURA_TG__NATS_URL` | Telegram | No | NATS server URL. Must use FQDN in cluster. |
| `AURA_TG__LOG_LEVEL` | Telegram | No | Logging level (default: info). |
| `AURA_TG__OTEL_EXPORTER_OTLP_ENDPOINT` | Telegram | No | Jaeger OTLP exporter endpoint. (Uses FQDN). |

## CI/CD and Helm Secret Keys

The following keys are used within the Kubernetes `aura-secrets` Secret, populated by Helm during deployment:

| Secret Key | Helm Value | CI/CD Secret |
|------------|------------|--------------|
| `api-key` | `secrets.llmApiKey` | `MISTRAL_API_KEY` |
| `openai-key` | `secrets.openaiApiKey` | `OPENAI_API_KEY` |
| `telegram-token` | `secrets.telegramToken` | `AURA_TELEGRAM_TOKEN` |
| `secret-encryption-key` | `secrets.secretEncryptionKey` | `AURA_SECRET_ENCRYPTION_KEY` |
| `solana-private-key` | `secrets.solanaPrivateKey` | `SOLANA_PRIVATE_KEY` |
| `frp-client-token` | `secrets.frpClientToken.value` | `FRP_CLIENT_TOKEN` |
