# Environment Variables Reference

This document provides a comprehensive reference for all environment variables used across AURA services.

## Table of Contents

- [Naming Convention](#naming-convention)
- [Core Service](#core-service)
- [Gateway Service](#gateway-service)
- [Telegram Bot Service](#telegram-bot-service)
- [Secret Management](#secret-management)
- [Deployment Checklist](#deployment-checklist)
- [Troubleshooting](#troubleshooting)

---

## Naming Convention

### Core Service (AURA_ prefix)

- **Prefix**: `AURA_`
- **Nested delimiter**: `__` (double underscore)
- **Format**: `AURA_<SECTION>__<FIELD_NAME>`
- **Examples**:
  - `AURA_DATABASE__URL`
  - `AURA_LLM__API_KEY`
  - `AURA_SERVER__NATS_URL`

### Gateway Service (No prefix - intentional)

Gateway intentionally uses plain environment variable names without the `AURA_` prefix:
- **Format**: `<FIELD_NAME>`
- **Examples**:
  - `CORE_SERVICE_HOST`
  - `REDIS_URL`
  - `LOG_LEVEL`

**Rationale**: Different architectural layer with independent configuration.

### Telegram Service (AURA_TG__ prefix)

- **Prefix**: `AURA_TG__`
- **Nested delimiter**: `__`
- **Format**: `AURA_TG__<FIELD_NAME>`

---

## Core Service

### Database Configuration

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `AURA_DATABASE__URL` | PostgresDsn | **None** | ✅ | PostgreSQL connection string |
| `AURA_DATABASE__REDIS_URL` | RedisDsn | **None** | ✅ | Redis connection string |
| `AURA_DATABASE__VECTOR_DIMENSION` | int | 1024 | ❌ | Vector embedding dimension |

**Examples**:
```bash
export AURA_DATABASE__URL="postgresql://user:pass@postgres:5432/aura_db"
export AURA_DATABASE__REDIS_URL="redis://redis:6379/0"
```

**⚠️ CRITICAL**: No localhost defaults. Service will fail at startup with clear error message if not set.

---

### LLM Configuration

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `AURA_LLM__MODEL` | str | mistral/mistral-large-latest | ✅ | LLM model identifier |
| `AURA_LLM__API_KEY` | SecretStr | Empty | Conditional* | Mistral API key |
| `AURA_LLM__OPENAI_API_KEY` | SecretStr | Empty | Conditional* | OpenAI API key |
| `AURA_LLM__TEMPERATURE` | float | 0.7 | ❌ | LLM temperature |
| `AURA_LLM__COMPILED_PROGRAM_PATH` | str | aura_brain.json | ❌ | DSPy compiled program path |

**\*Conditional Requirements**:
- `AURA_LLM__API_KEY` required for `mistral/*` models
- `AURA_LLM__OPENAI_API_KEY` required for `openai/*` models
- Neither required for rule-based mode (no LLM)

**Examples**:
```bash
# For Mistral models
export AURA_LLM__MODEL="mistral/mistral-large-latest"
export AURA_LLM__API_KEY="sk-..."

# For OpenAI models
export AURA_LLM__MODEL="openai/gpt-4"
export AURA_LLM__OPENAI_API_KEY="sk-..."

# Rule-based mode (no API key needed)
export AURA_LLM__MODEL="rule-based"
```

---

### Server Configuration

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `AURA_SERVER__HOST` | str | 0.0.0.0 | ✅ | gRPC bind address |
| `AURA_SERVER__PORT` | int | 50051 | ✅ | gRPC port |
| `AURA_SERVER__NATS_URL` | str | nats://nats:4222 | ✅ | NATS message broker URL |
| `AURA_SERVER__PROMETHEUS_URL` | HttpUrl | (K8s FQDN) | ✅ | Prometheus metrics endpoint |
| `AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT` | HttpUrl | (K8s FQDN) | ✅ | Jaeger tracing endpoint |

**Examples**:
```bash
export AURA_SERVER__HOST="0.0.0.0"
export AURA_SERVER__PORT="50051"
export AURA_SERVER__NATS_URL="nats://nats:4222"
export AURA_SERVER__PROMETHEUS_URL="http://aura-prometheus.monitoring.svc.cluster.local:9090"
export AURA_SERVER__OTEL_EXPORTER_OTLP_ENDPOINT="http://aura-jaeger.monitoring.svc.cluster.local:4317"
```

---

### Crypto Configuration

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `AURA_CRYPTO__ENABLED` | bool | false | ✅ | Enable blockchain payments |
| `AURA_CRYPTO__SOLANA_PRIVATE_KEY` | SecretStr | Empty | Conditional* | Solana wallet private key (Base58) |
| `AURA_CRYPTO__SECRET_ENCRYPTION_KEY` | SecretStr | Empty | Conditional* | Fernet encryption key (Base64) |

**\*Conditional**: Required if `AURA_CRYPTO__ENABLED=true`

**Examples**:
```bash
export AURA_CRYPTO__ENABLED="true"
export AURA_CRYPTO__SOLANA_PRIVATE_KEY="5J..."  # Base58 encoded
export AURA_CRYPTO__SECRET_ENCRYPTION_KEY="Zm9..."  # Base64 Fernet key
```

---

## Gateway Service

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `CORE_SERVICE_HOST` | str | localhost:50051 | ✅ | Core gRPC endpoint |
| `HTTP_PORT` | int | 8000 | ✅ | HTTP server port |
| `REDIS_URL` | str | **None** | ✅ | Redis connection string |
| `LOG_LEVEL` | str | info | ❌ | Logging level (debug/info/warning/error) |
| `OTEL_SERVICE_NAME` | str | aura-gateway | ✅ | OpenTelemetry service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | HttpUrl | (K8s FQDN) | ✅ | Jaeger tracing endpoint |
| `CORS_ORIGINS` | str | https://aura.zae.life | ✅ | Allowed CORS origins |
| `NEGOTIATION_TIMEOUT` | float | 60.0 | ❌ | Negotiation timeout (seconds) |
| `HEALTH_CHECK_TIMEOUT` | float | 2.0 | ❌ | Health check timeout (seconds) |
| `HEALTH_CHECK_SLOW_THRESHOLD_MS` | float | 100.0 | ❌ | Slow health check threshold (ms) |

**Examples**:
```bash
export CORE_SERVICE_HOST="aura-core:50051"
export REDIS_URL="redis://aura-redis:6379/0"
export LOG_LEVEL="info"
export CORS_ORIGINS="https://aura.zae.life,https://staging.aura.zae.life"
```

---

## Telegram Bot Service

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `AURA_TG__TOKEN` | SecretStr | Empty | ✅ | Telegram bot token |
| `AURA_TG__CORE_URL` | str | core:50051 | ✅ | Core service gRPC endpoint |
| `AURA_TG__NATS_URL` | str | nats://nats:4222 | ✅ | NATS message broker URL |
| `AURA_TG__OTEL_EXPORTER_OTLP_ENDPOINT` | HttpUrl | (K8s FQDN) | ✅ | Jaeger tracing endpoint |
| `LOG_LEVEL` | str | info | ✅ | Logging level |

**Examples**:
```bash
export AURA_TG__TOKEN="123456:ABC-DEF..."
export AURA_TG__CORE_URL="aura-core:50051"
export AURA_TG__NATS_URL="nats://aura-nats:4222"
export LOG_LEVEL="info"
```

---

## Secret Management

### GitHub Secrets → Kubernetes Secret Mapping

The CI/CD pipeline (`ci-cd.yaml`) creates Kubernetes secrets from GitHub secrets:

| GitHub Secret | K8s Secret Key | Environment Variable | Used By | Status |
|--------------|----------------|---------------------|---------|--------|
| `AURA_TELEGRAM_TOKEN` | `telegram-token` | `AURA_TG__TOKEN` | Telegram | ✅ OK |
| `MISTRAL_API_KEY` | `api-key` | `AURA_LLM__API_KEY` | Core | ✅ OK |
| `OPENAI_API_KEY` | `openai-key` | `AURA_LLM__OPENAI_API_KEY` | Core | ✅ OK (Fixed) |
| `AURA_SECRET_ENCRYPTION_KEY` | `secret-encryption-key` | `AURA_CRYPTO__SECRET_ENCRYPTION_KEY` | Core | ✅ OK |
| `SOLANA_PRIVATE_KEY` | `solana-private-key` | `AURA_CRYPTO__SOLANA_PRIVATE_KEY` | Core | ✅ OK |
| `FRP_CLIENT_TOKEN` | `frp-client-token` | N/A | None | 🟡 Unused |
| `AURA_INFRA_STCP_KEY` | `stcp-key` | `FRP_STCP_SECRET_KEY` | frpc tunnel | ✅ OK |

### Secret Creation (CI/CD)

**File**: `.github/workflows/ci-cd.yaml:187-194`

```yaml
kubectl create secret generic aura-secrets \
  --from-literal=telegram-token="$TG_TOKEN" \
  --from-literal=api-key="$API_KEY" \
  --from-literal=openai-key="$OPENAI_KEY" \
  --from-literal=secret-encryption-key="$ENC_KEY" \
  --from-literal=frp-client-token="$FRP_TOKEN" \
  --from-literal=solana-private-key="$SOL_KEY" \
  --from-literal=stcp-key="$STCP_KEY"
```

### Unused Secrets

**FRP_CLIENT_TOKEN**
- Created in CI/CD but never referenced in any deployment
- **Decision**: Documented only, kept for potential future use

**STCP_KEY (AURA_INFRA_STCP_KEY)**
- Used in `ona-dance.toml` for local FRP tunneling
- **Now used in production**: Injected as `FRP_STCP_SECRET_KEY` env var in frpc tunnel deployment
- **Purpose**: Secures STCP connection for NATS hidden tunnel
- **Decision**: Required secret, properly managed via Kubernetes Secret

---

## Deployment Checklist

Use this checklist before deploying:

### Required Environment Variables

- [ ] **Database**
  - [ ] `AURA_DATABASE__URL` configured
  - [ ] `AURA_DATABASE__REDIS_URL` configured
  - [ ] No localhost references in production

- [ ] **LLM** (if using AI models)
  - [ ] `AURA_LLM__MODEL` set
  - [ ] `AURA_LLM__API_KEY` set (for Mistral models)
  - [ ] `AURA_LLM__OPENAI_API_KEY` set (for OpenAI models)

- [ ] **Secrets**
  - [ ] All GitHub secrets configured
  - [ ] Kubernetes secrets created
  - [ ] Telegram bot token valid

- [ ] **Gateway**
  - [ ] `CORE_SERVICE_HOST` points to correct service
  - [ ] `REDIS_URL` configured
  - [ ] `CORS_ORIGINS` set for production

- [ ] **Monitoring**
  - [ ] Prometheus endpoint accessible
  - [ ] Jaeger endpoint accessible
  - [ ] Service names unique

### Validation Commands

```bash
# Test Helm template rendering
helm template aura ./deploy/aura --values ./deploy/aura/values.yaml > rendered.yaml

# Check for localhost references
grep -r "localhost" rendered.yaml

# Validate all ENV variables present
grep -E "AURA_|CORE_SERVICE_HOST|REDIS_URL|LOG_LEVEL" rendered.yaml

# Test config loading (locally)
export AURA_DATABASE__URL="postgresql://user:pass@localhost:5432/test"
export AURA_DATABASE__REDIS_URL="redis://localhost:6379/0"
PYTHONPATH=core:core/src python -c "from config import settings; print('✓ Config OK')"
```

---

## Troubleshooting

### Common Errors

#### "AURA_DATABASE__URL is required"

**Cause**: Missing or empty database URL
**Solution**:
```bash
export AURA_DATABASE__URL="postgresql://user:pass@host:5432/dbname"
```

#### "AURA_LLM__API_KEY is required for Mistral models"

**Cause**: Using Mistral model without API key
**Solution**:
```bash
export AURA_LLM__API_KEY="sk-..."
# OR switch to rule-based mode:
export AURA_LLM__MODEL="rule-based"
```

#### "cannot connect to redis://localhost:6379"

**Cause**: Localhost default was removed; REDIS_URL not set
**Solution**:
```bash
# Gateway service
export REDIS_URL="redis://aura-redis:6379/0"
# Core service
export AURA_DATABASE__REDIS_URL="redis://aura-redis:6379/0"
```

### Debugging Configuration

#### View current settings (Core)

```python
PYTHONPATH=core:core/src python -c "
from config import settings
print(f'Database URL: {settings.database.url}')
print(f'Redis URL: {settings.database.redis_url}')
print(f'LLM Model: {settings.llm.model}')
"
```

#### View current settings (Gateway)

```python
PYTHONPATH=api-gateway/src python -c "
from config import get_settings
s = get_settings()
print(f'Core Host: {s.core_service_host}')
print(f'Redis URL: {s.redis_url}')
print(f'Log Level: {s.log_level}')
"
```

#### Check Helm values

```bash
# Show computed values
helm get values aura

# Show all values (including defaults)
helm get values aura --all
```

### Validation Script

Use the automated verification script:

```bash
uv run python tools/verify_env.py
```

This script will:
- Parse all Pydantic config files
- Parse all Helm templates
- Compare and report mismatches
- Validate naming conventions
- Check for localhost defaults
- Report unused secrets

---

## Security Best Practices

1. **Never commit secrets to Git**
   - Use GitHub Secrets for CI/CD
   - Use Kubernetes Secrets for runtime
   - Use `.env` files locally (gitignored)

2. **Rotate secrets regularly**
   - API keys
   - Database passwords
   - Encryption keys

3. **Use least privilege**
   - Telegram bot: Only required permissions
   - Database user: Only required tables
   - Solana wallet: Minimal funding

4. **Validate at boundaries**
   - Pydantic validation for all ENV vars
   - Fail fast with clear error messages
   - No silent failures on missing config

5. **Monitor secret usage**
   - Track when secrets are accessed
   - Alert on authentication failures
   - Log configuration validation errors

---

## Additional Resources

- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [OpenTelemetry Configuration](https://opentelemetry.io/docs/instrumentation/python/manual/)

---

## Changelog

### 2026-02-05
- Fixed CI/CD OpenAI key bug (line 190: `$API_KEY` → `$OPENAI_KEY`)
- Removed database localhost defaults (fail-fast behavior)
- Added LLM API key validation
- Added Gateway `REDIS_URL` and `LOG_LEVEL` config
- Fixed Telegram bot NATS configuration (added `AURA_TG__NATS_URL` via Pydantic settings and Helm)
- Created master environment documentation
- Documented unused secrets (FRP_CLIENT_TOKEN, STCP_KEY)
