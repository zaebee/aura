"""NATS state in gateway health output: visible, never traffic-shaping.

Degraded-without-503 (product decision): a NATS drop shows up in
`/readyz` dependencies and `/health` checks, but readiness still follows
the Core Service alone. Traffic keeps flowing; the state word is for
operators, not for kubelet.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from api_gateway.health import register_health_endpoints
from fastapi import FastAPI
from fastapi.testclient import TestClient
from grpc_health.v1 import health_pb2


def _app(core_status: str, nats_state: str) -> FastAPI:
    """Health-only app: fake core stub + fixed NATS state word."""
    app = FastAPI()

    if core_status == "starting":
        stub = None
    elif core_status == "ok":
        stub = AsyncMock()
        stub.Check.return_value = SimpleNamespace(
            status=health_pb2.HealthCheckResponse.SERVING
        )
    else:
        stub = AsyncMock()
        stub.Check.side_effect = RuntimeError("core down")

    register_health_endpoints(
        app,
        get_stub=lambda: stub,
        health_check_timeout=1.0,
        get_nats_state=lambda: nats_state,
    )
    return app


def test_readyz_reports_nats_state_but_stays_ready() -> None:
    client = TestClient(_app("ok", "disconnected"))
    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["dependencies"]["nats"] == "disconnected"


@pytest.mark.parametrize("state", ["connected", "disconnected", "closed"])
def test_readyz_passes_nats_state_through(state: str) -> None:
    body = TestClient(_app("ok", state)).get("/readyz").json()
    assert body["dependencies"]["nats"] == state


def test_readyz_still_503_when_core_is_down_despite_nats() -> None:
    response = TestClient(_app("error", "connected")).get("/readyz")

    assert response.status_code == 503


def test_health_checks_include_both_core_and_nats() -> None:
    body = TestClient(_app("ok", "connected")).get("/health").json()

    assert body["status"] == "healthy"
    assert body["checks"]["nats"] == "connected"
    assert body["checks"]["core_service"] == "ok"


def test_health_degraded_when_core_down_lists_nats_anyway() -> None:
    body = TestClient(_app("error", "disconnected")).get("/health").json()

    assert body["status"] == "degraded"
    assert body["checks"]["nats"] == "disconnected"
