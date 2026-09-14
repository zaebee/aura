"""Probe rate limiting: floor binary-search stretched past price validity.

Each bid on one item is a probe: ~17 accept/reject answers recover a floor
at cent precision. The only mitigation that changes the picture is time —
a sliding window per (counterparty, item) that stretches 17 probes over
longer than a price stays valid, so the recovered number is stale.

Whitelisted counterparties (regular negotiators, indistinguishable from
slow probers by this signal alone) bypass the limiter entirely.
"""

import time

import httpx
import pytest
from api_gateway.probe_limit import ProbeLimiter

WHITELIST: frozenset[str] = frozenset()


def _limiter(redis_client, limit: int = 5, window_s: int = 3600) -> ProbeLimiter:
    return ProbeLimiter(
        redis_client,
        limit=limit,
        window_s=window_s,
        whitelist=WHITELIST,
    )


@pytest.mark.asyncio
async def test_first_probes_pass_until_limit() -> None:
    import fakeredis.aioredis

    limiter = _limiter(fakeredis.aioredis.FakeRedis())

    for _ in range(5):
        allowed, _ = await limiter.check("did:key:a", "item-1")
        assert allowed is True

    allowed, retry_after = await limiter.check("did:key:a", "item-1")
    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_counters_are_isolated_by_pair() -> None:
    import fakeredis.aioredis

    limiter = _limiter(fakeredis.aioredis.FakeRedis(), limit=1)

    allowed, _ = await limiter.check("did:key:a", "item-1")
    assert allowed is True

    # Same counterparty, other item: fresh budget.
    allowed, _ = await limiter.check("did:key:a", "item-2")
    assert allowed is True

    # Other counterparty, same item: fresh budget.
    allowed, _ = await limiter.check("did:key:b", "item-1")
    assert allowed is True

    # Same pair exhausted.
    allowed, _ = await limiter.check("did:key:a", "item-1")
    assert allowed is False


@pytest.mark.asyncio
async def test_window_slides_old_probes_out() -> None:
    import fakeredis.aioredis

    limiter = _limiter(fakeredis.aioredis.FakeRedis(), limit=1, window_s=3600)
    now = time.time()

    allowed, _ = await limiter.check("did:key:a", "item-1", now=now)
    assert allowed is True
    allowed, _ = await limiter.check("did:key:a", "item-1", now=now)
    assert allowed is False

    # Past the window: budget restored.
    allowed, _ = await limiter.check("did:key:a", "item-1", now=now + 3601)
    assert allowed is True


@pytest.mark.asyncio
async def test_whitelisted_counterparty_bypasses() -> None:
    import fakeredis.aioredis

    limiter = ProbeLimiter(
        fakeredis.aioredis.FakeRedis(),
        limit=1,
        window_s=3600,
        whitelist=frozenset({"did:key:regular"}),
    )

    for _ in range(5):
        allowed, _ = await limiter.check("did:key:regular", "item-1")
        assert allowed is True


@pytest.mark.asyncio
async def test_retry_after_fits_inside_window() -> None:
    import fakeredis.aioredis

    limiter = _limiter(fakeredis.aioredis.FakeRedis(), limit=1, window_s=600)
    now = time.time()

    await limiter.check("did:key:a", "item-1", now=now)
    _, retry_after = await limiter.check("did:key:a", "item-1", now=now)

    assert 0 < retry_after <= 600


@pytest.mark.asyncio
async def test_blocked_probes_do_not_extend_the_lockout() -> None:
    """Spamming while blocked must not push recovery further out."""
    import fakeredis.aioredis

    redis_client = fakeredis.aioredis.FakeRedis()
    limiter = _limiter(redis_client, limit=1, window_s=600)
    now = time.time()

    await limiter.check("did:key:a", "item-1", now=now)
    for _ in range(10):
        allowed, _ = await limiter.check("did:key:a", "item-1", now=now)
        assert allowed is False

    # Once the single real probe slides out, budget is back — the 10
    # blocked ones left no trace.
    allowed, _ = await limiter.check("did:key:a", "item-1", now=now + 601)
    assert allowed is True


def test_negotiate_returns_429_with_retry_after_when_limited() -> None:
    """429 wiring at the endpoint: shape, code, Retry-After header."""
    from unittest.mock import AsyncMock

    from api_gateway.main import app
    from api_gateway.security import verify_public_membrane
    from fastapi import Request
    from fastapi.testclient import TestClient

    async def _bypass(request: Request) -> str:
        request.state.parsed_body = {
            "item_id": "sku-1",
            "bid_amount": 100.0,
            "currency": "USD",
            "agent_did": "did:key:test",
        }
        return "did:key:test"

    limiter = AsyncMock()
    limiter.check.return_value = (False, 30.0)
    app.dependency_overrides[verify_public_membrane] = _bypass
    app.state.probe_limiter = limiter
    try:
        response = TestClient(app).post(
            "/v1/negotiate",
            json={
                "item_id": "sku-1",
                "bid_amount": 100.0,
                "currency": "USD",
                "agent_did": "did:key:test",
            },
            headers={
                "X-Agent-ID": "did:key:test",
                "X-Timestamp": "1234567890",
                "X-Signature": "fake-sig",
            },
        )
    finally:
        app.dependency_overrides.clear()
        app.state.probe_limiter = None

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json()["detail"] == "probe rate limit exceeded"


def test_negotiate_retry_after_never_zero() -> None:
    """A sub-second retry_after still tells the client to wait."""
    from unittest.mock import AsyncMock

    from api_gateway.main import app
    from api_gateway.security import verify_public_membrane
    from fastapi import Request
    from fastapi.testclient import TestClient

    async def _bypass(request: Request) -> str:
        request.state.parsed_body = {
            "item_id": "sku-1",
            "bid_amount": 100.0,
            "currency": "USD",
            "agent_did": "did:key:test",
        }
        return "did:key:test"

    limiter = AsyncMock()
    limiter.check.return_value = (False, 0.5)
    app.dependency_overrides[verify_public_membrane] = _bypass
    app.state.probe_limiter = limiter
    try:
        response = TestClient(app).post(
            "/v1/negotiate",
            json={
                "item_id": "sku-1",
                "bid_amount": 100.0,
                "currency": "USD",
                "agent_did": "did:key:test",
            },
            headers={
                "X-Agent-ID": "did:key:test",
                "X-Timestamp": "1234567890",
                "X-Signature": "fake-sig",
            },
        )
    finally:
        app.dependency_overrides.clear()
        app.state.probe_limiter = None

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


def _post_negotiate() -> httpx.Response:
    from unittest.mock import AsyncMock, patch

    from api_gateway.main import app
    from api_gateway.security import verify_public_membrane
    from aura_core_gen.aura.negotiation.v1 import NegotiateResponse
    from fastapi import Request
    from fastapi.testclient import TestClient

    async def _bypass(request: Request) -> str:
        request.state.parsed_body = {
            "item_id": "sku-1",
            "bid_amount": 100.0,
            "currency": "USD",
            "agent_did": "did:key:test",
        }
        return "did:key:test"

    mock_stub = AsyncMock()
    mock_stub.negotiate.return_value = NegotiateResponse(
        session_token="sess",
        valid_until_timestamp=1,
        dispute_token="tok",
    )
    app.dependency_overrides[verify_public_membrane] = _bypass
    try:
        with patch("api_gateway.main.stub", mock_stub, create=True):
            return TestClient(app).post(
                "/v1/negotiate",
                json={
                    "item_id": "sku-1",
                    "bid_amount": 100.0,
                    "currency": "USD",
                    "agent_did": "did:key:test",
                },
                headers={
                    "X-Agent-ID": "did:key:test",
                    "X-Timestamp": "1234567890",
                    "X-Signature": "fake-sig",
                },
            )
    finally:
        app.dependency_overrides.clear()
        app.state.probe_limiter = None


def test_negotiate_passes_through_when_limiter_fails() -> None:
    """Fail-open: a Redis outage at runtime degrades to unlimited, not 500."""
    from unittest.mock import AsyncMock

    from api_gateway.main import app

    limiter = AsyncMock()
    limiter.check.side_effect = RuntimeError("redis down")
    app.state.probe_limiter = limiter

    response = _post_negotiate()

    assert response.status_code == 200
