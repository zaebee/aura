"""Lightweight health-check HTTP server for the Telegram synapse.

Runs alongside the bot as a background asyncio task and exposes
Kubernetes-compatible probe endpoints:

- /healthz  — liveness  (process alive)
- /readyz   — readiness (bot polling + NATS connected)
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiohttp import web

# --------------- shared state (set by main.py) ---------------


class _ProbeState:
    """Mutable health state updated by the main loop."""

    bot_polling: bool = False
    nats_connected: bool = False


state = _ProbeState()

# --------------- handlers ---------------


async def _healthz(request: web.Request) -> web.Response:
    """Liveness: always 200 if the process is running."""
    return web.json_response({"status": "ok"})


async def _readyz(request: web.Request) -> web.Response:
    """Readiness: 200 only when bot is polling and NATS is up."""
    checks = {
        "bot_polling": state.bot_polling,
        "nats_connected": state.nats_connected,
    }
    ready = all(checks.values())
    body = {
        "status": "ready" if ready else "not_ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
    }
    return web.json_response(body, status=200 if ready else 503)


# --------------- server lifecycle ---------------


async def start_health_server(port: int) -> web.AppRunner:
    """Create and start the health HTTP server, return the runner."""
    app = web.Application()
    app.router.add_get("/healthz", _healthz)
    app.router.add_get("/readyz", _readyz)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)  # nosec B104 - container needs all interfaces
    await site.start()
    return runner
