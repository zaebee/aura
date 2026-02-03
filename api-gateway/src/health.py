"""Health check endpoints and utilities for API Gateway.

This module provides Kubernetes-compatible health check endpoints:
- /healthz: Liveness probe (simple alive check)
- /readyz: Readiness probe (checks dependencies)
- /health: Detailed health status with metrics

All health checks are designed to be fast (<100ms) and lightweight.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

import grpc
from fastapi import FastAPI, HTTPException
from grpc_health.v1 import health_pb2, health_pb2_grpc
from pydantic import BaseModel, Field

from src.logging_config import get_logger

logger = get_logger("health")


class HealthStatus(str, Enum):
    """Health check status values."""

    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class HealthCheckResult:
    """Result of a health check operation.

    Attributes:
        status: Health status (OK, TIMEOUT, or ERROR)
        message: Optional human-readable message
        latency_ms: Response time in milliseconds
    """

    status: HealthStatus
    message: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Response model for /health endpoint.

    Provides detailed system health information including component statuses.
    """

    status: str = Field(..., description="Overall system health status")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    version: str = Field(..., description="API version")
    checks: dict[str, str] = Field(..., description="Individual component statuses")


class ReadinessResponse(BaseModel):
    """Response model for /readyz endpoint."""

    status: str = Field(..., description="Readiness status")
    dependencies: dict[str, str] = Field(..., description="Dependency statuses")


async def check_core_service_health(
    health_stub: health_pb2_grpc.HealthStub, timeout: float
) -> HealthCheckResult:
    """Check Core Service health using gRPC Health Checking Protocol.

    Calls the standardized gRPC Health service on the Core Service to verify
    it is ready to handle requests. This tests the full RPC stack including
    database connectivity.

    Args:
        health_stub: gRPC Health service stub for Core Service
        timeout: Maximum time to wait for response in seconds

    Returns:
        HealthCheckResult: Object containing status, optional error message,
            and connection latency in milliseconds.

    Note:
        Uses the official gRPC Health Checking Protocol (grpc.health.v1.Health)
        which verifies database connectivity on the Core Service side.
    """
    start_time = time.perf_counter()

    try:
        request = health_pb2.HealthCheckRequest(service="")
        response = await asyncio.wait_for(health_stub.Check(request), timeout=timeout)

        latency_ms = (time.perf_counter() - start_time) * 1000

        if response.status == health_pb2.HealthCheckResponse.SERVING:
            logger.debug(
                "core_service_health_check_ok",
                latency_ms=round(latency_ms, 2),
                status="serving",
            )
            return HealthCheckResult(
                status=HealthStatus.OK, latency_ms=round(latency_ms, 2)
            )
        else:
            logger.warning(
                "core_service_health_check_not_serving",
                response_status=response.status,
                latency_ms=round(latency_ms, 2),
            )
            return HealthCheckResult(
                status=HealthStatus.ERROR,
                message=f"Core service status: {response.status}",
                latency_ms=round(latency_ms, 2),
            )

    except TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "core_service_health_check_timeout",
            timeout_seconds=timeout,
            latency_ms=round(latency_ms, 2),
        )
        return HealthCheckResult(
            status=HealthStatus.TIMEOUT,
            message=f"Timeout after {timeout}s",
            latency_ms=round(latency_ms, 2),
        )

    except grpc.RpcError as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        if e.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
            logger.warning(
                "core_service_health_check_timeout",
                timeout_seconds=timeout,
                latency_ms=round(latency_ms, 2),
                source="grpc",
            )
            return HealthCheckResult(
                status=HealthStatus.TIMEOUT,
                message=f"gRPC deadline exceeded after {timeout}s",
                latency_ms=round(latency_ms, 2),
            )

        logger.error(
            "core_service_health_check_rpc_error",
            code=e.code(),
            details=e.details(),
            latency_ms=round(latency_ms, 2),
        )
        return HealthCheckResult(
            status=HealthStatus.ERROR,
            message="RPC call failed",
            latency_ms=round(latency_ms, 2),
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            "core_service_health_check_error",
            error=str(e),
            latency_ms=round(latency_ms, 2),
            exc_info=True,
        )
        return HealthCheckResult(
            status=HealthStatus.ERROR,
            message="Service unreachable",
            latency_ms=round(latency_ms, 2),
        )


def register_health_endpoints(
    app: FastAPI,
    health_stub: health_pb2_grpc.HealthStub,
    health_check_timeout: float,
    slow_threshold_ms: float = 100.0,
) -> None:
    """Register health check endpoints on FastAPI application.

    Args:
        app: FastAPI application instance
        health_stub: gRPC Health service stub for checking Core Service
        health_check_timeout: Timeout for health checks in seconds
        slow_threshold_ms: Log warning if health check exceeds this duration
    """

    @app.get("/healthz")
    async def liveness() -> dict[str, str]:
        """Liveness probe endpoint.

        Simple check to verify the API Gateway process is alive and responding.
        This endpoint always returns 200 OK if the process is running.

        Used by Kubernetes liveness probe to detect deadlocks or crashes.
        If this fails repeatedly, the container will be restarted.

        Returns:
            dict: Always {"status": "ok"}
        """
        return {"status": "ok"}

    @app.get("/readyz", response_model=ReadinessResponse)
    async def readiness() -> ReadinessResponse:
        """Readiness probe endpoint.

        Checks if the API Gateway is ready to handle traffic by verifying
        connectivity to the Core Service. Returns 503 if any dependencies
        are unhealthy.

        Used by Kubernetes readiness probe to control traffic routing.
        If this fails, the pod is removed from load balancer rotation.

        Returns:
            ReadinessResponse: Status and dependency information

        Raises:
            HTTPException: 503 if not ready to handle traffic
        """
        start_time = time.perf_counter()
        core_status = await check_core_service_health(health_stub, health_check_timeout)

        check_duration_ms = (time.perf_counter() - start_time) * 1000
        if check_duration_ms > slow_threshold_ms:
            logger.warning(
                "readiness_check_slow",
                duration_ms=round(check_duration_ms, 2),
                threshold_ms=slow_threshold_ms,
            )

        if core_status.status != HealthStatus.OK:
            logger.info(
                "readiness_check_not_ready",
                core_service_status=core_status.status.value,
                core_service_message=core_status.message,
                duration_ms=round(check_duration_ms, 2),
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not_ready",
                    "dependencies": {"core_service": core_status.status.value},
                },
            )

        return ReadinessResponse(
            status="ready", dependencies={"core_service": HealthStatus.OK.value}
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Detailed health status endpoint.

        Provides comprehensive health information including:
        - Overall system status (healthy/degraded)
        - Timestamp of the check
        - API version
        - Status of individual components

        This endpoint always returns 200 OK and provides status details
        in the response body. Use /readyz for traffic routing decisions.

        Returns:
            HealthResponse: Detailed health information
        """
        start_time = time.perf_counter()
        core_status = await check_core_service_health(health_stub, health_check_timeout)

        check_duration_ms = (time.perf_counter() - start_time) * 1000
        if check_duration_ms > slow_threshold_ms:
            logger.warning(
                "health_check_slow",
                duration_ms=round(check_duration_ms, 2),
                threshold_ms=slow_threshold_ms,
            )

        overall_status = (
            "healthy" if core_status.status == HealthStatus.OK else "degraded"
        )

        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(UTC).isoformat(),
            version=app.version,
            checks={
                "api_gateway": HealthStatus.OK.value,
                "core_service": core_status.status.value,
            },
        )
