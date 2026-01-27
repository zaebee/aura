# Health Check Implementation

This document describes the health check endpoints and probes implemented in the Aura platform.

## Overview

Health checks are implemented at three levels:
1. **API Gateway** - HTTP health endpoints
2. **Core Service** - gRPC Health Checking Protocol
3. **Docker Compose & Kubernetes** - Container orchestration probes

## API Gateway Health Endpoints

### `/healthz` - Liveness Probe
**Purpose**: Simple alive check - is the process running?

**Response**:
```json
{
  "status": "ok"
}
```

**HTTP Status**: 200 OK

**Use case**: Kubernetes liveness probe - restart if failing

---

### `/readyz` - Readiness Probe
**Purpose**: Full dependency check - is service ready to handle traffic?

**Response (healthy)**:
```json
{
  "status": "ready",
  "dependencies": {
    "core_service": "ok"
  }
}
```

**Response (unhealthy)**:
```json
{
  "status": "not_ready",
  "dependencies": {
    "core_service": "timeout"
  }
}
```

**HTTP Status**:
- 200 OK if ready
- 503 Service Unavailable if not ready

**Use case**: Kubernetes readiness probe - remove from load balancer if failing

---

### `/health` - Detailed Status
**Purpose**: Human-readable health information with component status

**Response**:
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

**HTTP Status**: 200 OK

**Use case**: Monitoring dashboards, debugging, status pages

---

## Core Service gRPC Health

The Core Service implements the standard [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md).

### Implementation Details

**Service**: `grpc.health.v1.Health`

**Check Method**: Verifies database connectivity
- Executes `SELECT 1` against PostgreSQL
- Returns `SERVING` if successful
- Returns `NOT_SERVING` if database unreachable

**Watch Method**: Not implemented (returns UNIMPLEMENTED)

### Testing with grpc_health_probe

```bash
# Install grpc_health_probe
go install github.com/grpc-ecosystem/grpc-health-probe@latest

# Test health
grpc_health_probe -addr=localhost:50051

# Expected output:
# status: SERVING
```

---

## Kubernetes Probes

### Gateway Deployment Probes

**Liveness Probe**:
- Endpoint: `GET /healthz`
- Initial delay: 10s
- Period: 10s
- Timeout: 5s
- Failure threshold: 3 (30s total before restart)

**Readiness Probe**:
- Endpoint: `GET /readyz`
- Initial delay: 5s
- Period: 5s
- Timeout: 3s
- Failure threshold: 2 (10s total before removing from LB)

**Startup Probe**:
- Endpoint: `GET /healthz`
- Initial delay: 0s
- Period: 2s
- Failure threshold: 30 (60s total startup time allowed)

### Core Service Deployment Probes

**Liveness Probe**:
- Type: gRPC
- Port: 50051
- Initial delay: 15s
- Period: 20s
- Timeout: 5s
- Failure threshold: 3

**Readiness Probe**:
- Type: gRPC
- Port: 50051
- Initial delay: 5s
- Period: 10s
- Timeout: 3s
- Failure threshold: 2

---

## Docker Compose Health Checks

### Database (PostgreSQL)
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U user -d aura_db"]
  interval: 5s
  timeout: 5s
  retries: 5
```

### Core Service
```yaml
healthcheck:
  test: ["CMD", "grpc_health_probe", "-addr=:50051"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Note**: Requires `grpc_health_probe` binary in the Docker image.

### API Gateway
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Note**: Requires `curl` binary in the Docker image.

### Frontend
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

---

## Testing Health Endpoints

### Manual Testing

```bash
# Start services
docker-compose up -d

# Test liveness
curl http://localhost:8000/healthz

# Test readiness
curl http://localhost:8000/readyz

# Test detailed health
curl http://localhost:8000/health

# Test gRPC health
grpc_health_probe -addr=localhost:50051

# Check Docker Compose health status
docker-compose ps
```

### Automated Testing

Run the comprehensive test suite:

```bash
# Ensure services are running
docker-compose up -d

# Wait for services to be ready
sleep 5

# Run tests
python test_health_endpoints.py
```

### Kubernetes Testing

```bash
# Check pod status
kubectl get pods -l app=gateway

# Verify probes in pod description
kubectl describe pod <gateway-pod-name>

# Check events for probe failures
kubectl get events --field-selector involvedObject.name=<pod-name>

# Test readiness endpoint from another pod
kubectl exec -it <gateway-pod> -- curl http://localhost:8000/readyz
```

---

## Probe Configuration Rationale

### Liveness Probe
- **Purpose**: Detect deadlocks, infinite loops, crashes
- **Failure threshold**: 3 failures = 30s before restart
- **Why**: Prevent premature restarts due to temporary slowness

### Readiness Probe
- **Purpose**: Manage traffic routing based on dependency health
- **Failure threshold**: 2 failures = 10s before removing from LB
- **Why**: Quickly remove unhealthy instances from load balancer

### Startup Probe
- **Purpose**: Protect slow-starting containers from premature restarts
- **Failure threshold**: 30 failures = 60s startup window
- **Why**: Allow sufficient time for service initialization and dependency checks

---

## Monitoring and Alerting

### Recommended Metrics

1. **Health check success rate**: Track percentage of successful health checks
2. **Time to ready**: Measure how long services take to become ready
3. **Probe failure count**: Alert on repeated probe failures
4. **Dependency status**: Monitor core_service connectivity from gateway

### Prometheus Integration (Future)

Consider adding a `/metrics` endpoint with:
- `health_check_total{endpoint, status}` - Counter of health checks
- `health_check_duration_seconds{endpoint}` - Histogram of check duration
- `dependency_status{service}` - Gauge of dependency health (0/1)

---

## Troubleshooting

### Gateway readiness probe failing

1. Check core service connectivity:
   ```bash
   kubectl logs <gateway-pod>
   # Look for "core_service": "timeout" or "error"
   ```

2. Verify core service is running:
   ```bash
   kubectl get pods -l app=core
   ```

3. Test gRPC connectivity manually:
   ```bash
   kubectl exec -it <gateway-pod> -- grpc_health_probe -addr=<core-service>:50051
   ```

### Core service health check failing

1. Check database connectivity:
   ```bash
   kubectl logs <core-pod>
   # Look for database connection errors
   ```

2. Verify PostgreSQL is accessible:
   ```bash
   kubectl get pods -l app=postgres
   ```

3. Test database connection:
   ```bash
   kubectl exec -it <core-pod> -- psql -U user -d aura_db -c "SELECT 1"
   ```

### Docker Compose health checks failing

1. Check service logs:
   ```bash
   docker-compose logs core-service
   docker-compose logs api-gateway
   ```

2. Verify health check command works:
   ```bash
   docker-compose exec api-gateway curl -f http://localhost:8000/healthz
   docker-compose exec core-service grpc_health_probe -addr=:50051
   ```

3. Check if required binaries are present:
   ```bash
   docker-compose exec api-gateway which curl
   docker-compose exec core-service which grpc_health_probe
   ```

---

## Security Considerations

1. **No authentication**: Health endpoints are public by design for K8s/LB access
2. **Minimal information**: Endpoints expose only necessary status information
3. **No secrets**: Health responses never include credentials or sensitive data
4. **Rate limiting**: Consider adding light rate limiting to prevent abuse

---

## Dependencies

### Python Packages
- `grpcio-health-checking>=1.76.0` - gRPC health service implementation

### Docker Images
**API Gateway Dockerfile** should include:
```dockerfile
RUN apt-get update && apt-get install -y curl
```

**Core Service Dockerfile** should include:
```dockerfile
RUN go install github.com/grpc-ecosystem/grpc-health-probe@latest
ENV PATH="${PATH}:/root/go/bin"
```

---

## References

- [Kubernetes Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
- [Docker Compose Healthcheck](https://docs.docker.com/compose/compose-file/compose-file-v3/#healthcheck)
- [grpc_health_probe Tool](https://github.com/grpc-ecosystem/grpc-health-probe)
