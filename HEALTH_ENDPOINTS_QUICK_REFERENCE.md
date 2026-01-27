# Health Endpoints Quick Reference

## API Gateway HTTP Endpoints

| Endpoint | Purpose | Response | Status Codes |
|----------|---------|----------|--------------|
| `GET /healthz` | Liveness probe | `{"status": "ok"}` | 200 OK |
| `GET /readyz` | Readiness probe | `{"status": "ready", "dependencies": {...}}` | 200 OK / 503 Unavailable |
| `GET /health` | Detailed health | `{"status": "healthy", "timestamp": "...", ...}` | 200 OK |

## Core Service gRPC Health

| Service | Method | Response |
|---------|--------|----------|
| `grpc.health.v1.Health` | `Check()` | `SERVING` / `NOT_SERVING` |

## Kubernetes Probes

### Gateway

| Probe | Endpoint | Delay | Period | Timeout | Failures |
|-------|----------|-------|--------|---------|----------|
| Liveness | `/healthz` | 10s | 10s | 5s | 3 |
| Readiness | `/readyz` | 5s | 5s | 3s | 2 |
| Startup | `/healthz` | 0s | 2s | 5s | 30 |

### Core Service

| Probe | Type | Delay | Period | Timeout | Failures |
|-------|------|-------|--------|---------|----------|
| Liveness | gRPC | 15s | 20s | 5s | 3 |
| Readiness | gRPC | 5s | 10s | 3s | 2 |

## Docker Compose Health Checks

| Service | Test Command | Interval | Timeout | Retries |
|---------|--------------|----------|---------|---------|
| db | `pg_isready -U user -d aura_db` | 5s | 5s | 5 |
| core-service | `grpc_health_probe -addr=:50051` | 10s | 5s | 3 |
| api-gateway | `curl -f http://localhost:8000/healthz` | 10s | 5s | 3 |
| frontend | `curl -f http://localhost:3000` | 10s | 5s | 3 |

## Testing Commands

```bash
# HTTP endpoints
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
curl http://localhost:8000/health

# gRPC health
grpc_health_probe -addr=localhost:50051

# Docker Compose status
docker-compose ps

# Kubernetes pod status
kubectl get pods -l app=gateway
kubectl get pods -l app=core
```

## Dependencies Checked

| Service | Checks |
|---------|--------|
| API Gateway | Core Service gRPC connectivity (2s timeout) |
| Core Service | PostgreSQL connectivity (`SELECT 1`) |

## Response Examples

### `/healthz` (Liveness)
```json
{
  "status": "ok"
}
```

### `/readyz` (Readiness - Healthy)
```json
{
  "status": "ready",
  "dependencies": {
    "core_service": "ok"
  }
}
```

### `/readyz` (Readiness - Unhealthy)
```json
{
  "status": "not_ready",
  "dependencies": {
    "core_service": "timeout"
  }
}
```
*Status Code: 503 Service Unavailable*

### `/health` (Detailed)
```json
{
  "status": "healthy",
  "timestamp": "2026-01-27T12:34:56.789012+00:00",
  "version": "0.1.0",
  "checks": {
    "api_gateway": "ok",
    "core_service": "ok"
  }
}
```

### gRPC Health Check
```
status: SERVING
```
